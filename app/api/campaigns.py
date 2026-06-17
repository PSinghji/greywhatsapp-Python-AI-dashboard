"""
Campaigns API v2 - Create and manage message campaigns.

MAJOR CHANGES:
1. Wake-up signal: On campaign start, sends pendingCommand="wake_up" to all assigned devices
2. Dynamic task assignment: Tasks created WITHOUT deviceId - assigned dynamically by round-robin
3. Multi-media support: Campaigns can have up to 4 media items (2 images + 1 PDF + 1 video)
4. Retry with device shuffling: Failed tasks get reassigned to different devices
5. Anti-blocking: Increased default timing gaps
"""
from fastapi import APIRouter, HTTPException
from bson import ObjectId
from datetime import datetime, timezone
import random
import logging

from app.database import get_db
from app.models.schemas import CampaignCreate, CampaignUpdate, TaskStatus

logger = logging.getLogger(__name__)
router = APIRouter()


def serialize(doc):
    if doc is None:
        return None
    doc["_id"] = str(doc["_id"])
    return doc


async def log_activity(event_type: str, message: str, device_id: str = None,
                       campaign_id: str = None, task_id: str = None,
                       level: str = "info", metadata: dict = None):
    """Log an activity event to the activity_logs collection."""
    try:
        db = get_db()
        doc = {
            "eventType": event_type,
            "deviceId": device_id,
            "campaignId": campaign_id,
            "taskId": task_id,
            "message": message,
            "level": level,
            "metadata": metadata,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        await db.activity_logs.insert_one(doc)
    except Exception:
        pass


# @router.get("")
# async def list_campaigns():
#     """List all campaigns with stats."""
#     db = get_db()
#     campaigns = await db.campaigns.find().sort("createdAt", -1).to_list(500)
#     result = []
#     for c in campaigns:
#         cid = str(c["_id"])
#         sent = await db.tasks.count_documents({"campaignId": cid, "status": "completed"})
#         failed = await db.tasks.count_documents({"campaignId": cid, "status": "failed"})
#         pending = await db.tasks.count_documents({"campaignId": cid, "status": {"$in": ["pending", "assigned", "in_progress"]}})
#         invalid = await db.tasks.count_documents({"campaignId": cid, "status": "invalid_number"})
#         restricted = await db.tasks.count_documents({"campaignId": cid, "status": "account_restricted"})
#         c["_id"] = cid
#         c["stats"] = {"sent": sent, "failed": failed, "pending": pending, "invalid": invalid, "restricted": restricted}
#         result.append(c)
#     return result

@router.get("")
async def list_campaigns(limit: int = 50, skip: int = 0):
    db = get_db()
    # 1. Fetch campaigns with pagination
    campaigns = await db.campaigns.find().sort("createdAt", -1).skip(skip).limit(limit).to_list(limit)
    
    # 2. Get all campaign IDs for a bulk stats query
    campaign_ids = [str(c["_id"]) for c in campaigns]
    
    # 3. Perform a single aggregation to get all stats at once
    stats_pipeline = [
        {"$match": {"campaignId": {"$in": campaign_ids}}},
        {"$group": {
            "_id": "$campaignId",
            "sent": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}},
            "failed": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}},
            "pending": {"$sum": {"$cond": [{"$in": ["$status", ["pending", "assigned", "in_progress"]]}, 1, 0]}},
            "invalid": {"$sum": {"$cond": [{"$eq": ["$status", "invalid_number"]}, 1, 0]}},
            "restricted": {"$sum": {"$cond": [{"$eq": ["$status", "account_restricted"]}, 1, 0]}}
        }}
    ]
    
    stats_results = await db.tasks.aggregate(stats_pipeline).to_list(None)
    stats_map = {s["_id"]: s for s in stats_results}

    # 4. Merge stats into campaign objects
    result = []
    for c in campaigns:
        cid = str(c["_id"])
        c["_id"] = cid
        c["stats"] = stats_map.get(cid, {"sent": 0, "failed": 0, "pending": 0, "invalid": 0, "restricted": 0})
        # Remove _id from nested dict for clean JSON
        if "_id" in c["stats"]: del c["stats"]["_id"]
        result.append(c)
        
    return result

@router.get("/stats")
async def campaign_stats():
    """Get campaign statistics."""
    db = get_db()
    total = await db.campaigns.count_documents({})
    active = await db.campaigns.count_documents({"status": "running"})
    paused = await db.campaigns.count_documents({"status": "paused"})
    completed = await db.campaigns.count_documents({"status": "completed"})
    total_sent = await db.tasks.count_documents({"status": "completed"})
    total_failed = await db.tasks.count_documents({"status": "failed"})
    total_pending = await db.tasks.count_documents({"status": {"$in": ["pending", "assigned", "in_progress"]}})
    total_invalid = await db.tasks.count_documents({"status": "invalid_number"})
    total_restricted = await db.tasks.count_documents({"status": "account_restricted"})
    return {
        "total": total,
        "active": active,
        "paused": paused,
        "completed": completed,
        "totalSent": total_sent,
        "totalFailed": total_failed,
        "totalPending": total_pending,
        "totalInvalid": total_invalid,
        "totalRestricted": total_restricted,
    }


@router.post("")
async def create_campaign(data: CampaignCreate):
    """Create a new campaign with optional multi-media support."""
    db = get_db()
    # Remove duplicate recipients
    unique_recipients = list(dict.fromkeys(data.recipients))

    campaign = {
        "name": data.name,
        "description": data.description,
        "status": "draft",
        "recipients": unique_recipients,
        "messages": [m.model_dump() for m in data.messages],
        "tuningProfileId": data.tuningProfileId,
        "assignedDevices": data.assignedDevices,
        "accountType": getattr(data, 'accountType', None),
        "scheduledAt": data.scheduledAt,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    result = await db.campaigns.insert_one(campaign)
    campaign["_id"] = str(result.inserted_id)
    await log_activity("campaign_created", f"Campaign '{data.name}' created with {len(unique_recipients)} recipients",
                       campaign_id=campaign["_id"],
                       metadata={"recipientCount": len(unique_recipients), "messageCount": len(data.messages)})
    return campaign


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: str):
    """Get a single campaign."""
    db = get_db()
    try:
        campaign = await db.campaigns.find_one({"_id": ObjectId(campaign_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign ID")
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return serialize(campaign)


@router.put("/{campaign_id}")
async def update_campaign(campaign_id: str, data: CampaignUpdate):
    """Update a campaign."""
    db = get_db()
    update_data = {}
    for k, v in data.model_dump().items():
        if v is not None:
            if k == "messages":
                update_data[k] = [m if isinstance(m, dict) else m.model_dump() for m in v]
            else:
                update_data[k] = v
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    update_data["updatedAt"] = datetime.now(timezone.utc).isoformat()
    try:
        result = await db.campaigns.update_one(
            {"_id": ObjectId(campaign_id)}, {"$set": update_data}
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign ID")
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {"success": True}


@router.delete("/{campaign_id}")
async def delete_campaign(campaign_id: str):
    """Delete a campaign and its tasks."""
    db = get_db()
    try:
        campaign = await db.campaigns.find_one({"_id": ObjectId(campaign_id)})
        result = await db.campaigns.delete_one({"_id": ObjectId(campaign_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign ID")
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await db.tasks.delete_many({"campaignId": campaign_id})
    await log_activity("campaign_deleted",
                       f"Campaign '{campaign.get('name', campaign_id)}' deleted",
                       campaign_id=campaign_id, level="warning")
    return {"success": True}


@router.post("/{campaign_id}/start")
async def start_campaign(campaign_id: str):
    """Start a campaign - generate tasks and send wake-up to devices.
    
    CHANGES v2:
    - Tasks are created WITHOUT deviceId (assigned dynamically by round-robin in agent.py)
    - Sends wake-up command to all assigned/online devices
    - Anti-blocking: increased default timing gaps
    """
    db = get_db()
    try:
        campaign = await db.campaigns.find_one({"_id": ObjectId(campaign_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign ID")
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if not campaign.get("recipients"):
        raise HTTPException(status_code=400, detail="No recipients in campaign")
    if not campaign.get("messages"):
        raise HTTPException(status_code=400, detail="No messages in campaign")

    assigned_devices = campaign.get("assignedDevices", [])
    
    # Get ALL devices (online + offline) for wake-up
    # NOTE: field is 'status' not 'accountStatus' in the devices collection
    all_devices = await db.devices.find({
        "status": {"$nin": ["restricted", "blocked"]}
    }).to_list(500)
    all_device_ids = [d["deviceId"] for d in all_devices]
    
    if not assigned_devices:
        # Auto-assign to all non-restricted devices
        assigned_devices = all_device_ids
        if not assigned_devices:
            raise HTTPException(status_code=400, detail="No available devices")

    # ═══ WAKE-UP: Send wake_up command to ALL assigned devices ═══
    # This includes offline devices - they'll get the command on next heartbeat
    now = datetime.now(timezone.utc).isoformat()
    wake_up_count = 0
    woken_device_ids = []
    for device_id in assigned_devices:
        result = await db.devices.update_one(
            {"deviceId": device_id},
            {"$set": {"pendingCommand": "wake_up", "updatedAt": now}}
        )
        if result.modified_count > 0 or result.matched_count > 0:
            wake_up_count += 1
            woken_device_ids.append(device_id)
    
    logger.info(f"[Campaign Start] Sent wake_up to {wake_up_count} devices: {woken_device_ids}")
    
    # Log individual wake-up for each device so it shows in activity logs with device ID
    for did in woken_device_ids:
        await log_activity("wake_up_sent",
                           f"Wake-up command sent to device {did} for campaign '{campaign['name']}'",
                           device_id=did, campaign_id=campaign_id,
                           metadata={"campaignName": campaign["name"]})

    # Get tuning profile
    tuning = None
    if campaign.get("tuningProfileId"):
        try:
            tuning = await db.tuning_profiles.find_one({"_id": ObjectId(campaign["tuningProfileId"])})
        except Exception:
            pass
    if not tuning:
        tuning = await db.tuning_profiles.find_one({"isDefault": True})

    tuning_data = {}
    if tuning:
        tuning_data = {k: v for k, v in tuning.items() if k not in ["_id", "name", "description", "isDefault"]}

    # ═══ ANTI-BLOCKING: Increase default timing if not set ═══
    if "betweenRecipientsMin" not in tuning_data:
        tuning_data["betweenRecipientsMin"] = 8000   # 8 seconds min between recipients
    if "betweenRecipientsMax" not in tuning_data:
        tuning_data["betweenRecipientsMax"] = 20000   # 20 seconds max between recipients
    if "messageDelayMin" not in tuning_data:
        tuning_data["messageDelayMin"] = 3000         # 3 seconds min between messages
    if "messageDelayMax" not in tuning_data:
        tuning_data["messageDelayMax"] = 8000         # 8 seconds max between messages

    # Get accountType from campaign
    account_type = campaign.get("accountType", None)

    # ═══ DYNAMIC TASK CREATION: NO deviceId pre-assignment ═══
    # Tasks are created with deviceId=None - round-robin assigns them at fetch time
    tasks = []
    recipients = campaign["recipients"]
    messages = campaign["messages"]

    for i, recipient in enumerate(recipients):
        # Pick a random message template for variety
        message = random.choice(messages) if len(messages) > 1 else messages[0]

        task = {
            "campaignId": str(campaign["_id"]),
            "campaignName": campaign["name"],
            "deviceId": None,  # ← DYNAMIC: assigned at fetch time by round-robin
            "recipient": recipient,
            "message": message,
            "tuning": tuning_data,
            "accountType": account_type,
            "status": "pending",
            "retryCount": 0,
            "maxRetries": tuning_data.get("maxRetries", 3),
            "createdAt": now,
            "updatedAt": now,
            "assignedAt": None,
            "errorMessage": None,
            "deliveredAt": None,
        }
        tasks.append(task)

    if tasks:
        # Shuffle tasks for randomness
        random.shuffle(tasks)
        await db.tasks.insert_many(tasks)

    # Update campaign status
    await db.campaigns.update_one(
        {"_id": ObjectId(campaign_id)},
        {"$set": {
            "status": "running",
            "assignedDevices": assigned_devices,
            "startedAt": now,
            "updatedAt": now,
        }}
    )

    await log_activity("campaign_started",
                       f"Campaign '{campaign['name']}' started: {len(tasks)} tasks, "
                       f"{len(assigned_devices)} devices, {wake_up_count} wake-ups sent",
                       campaign_id=campaign_id,
                       metadata={"tasksCreated": len(tasks), "devices": assigned_devices,
                                "wakeUpsSent": wake_up_count})

    return {"success": True, "tasksCreated": len(tasks),
            "devicesAssigned": len(assigned_devices), "wakeUpsSent": wake_up_count}


@router.post("/{campaign_id}/pause")
async def pause_campaign(campaign_id: str):
    """Pause a running campaign."""
    db = get_db()
    try:
        result = await db.campaigns.update_one(
            {"_id": ObjectId(campaign_id), "status": "running"},
            {"$set": {"status": "paused", "updatedAt": datetime.now(timezone.utc).isoformat()}}
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign ID")
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Campaign not found or not running")
    await log_activity("campaign_paused", f"Campaign {campaign_id} paused",
                       campaign_id=campaign_id, level="warning")
    return {"success": True}


@router.post("/{campaign_id}/resume")
async def resume_campaign(campaign_id: str):
    """Resume a paused campaign."""
    db = get_db()
    try:
        result = await db.campaigns.update_one(
            {"_id": ObjectId(campaign_id), "status": "paused"},
            {"$set": {"status": "running", "updatedAt": datetime.now(timezone.utc).isoformat()}}
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign ID")
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Campaign not found or not paused")
    await log_activity("campaign_resumed", f"Campaign {campaign_id} resumed",
                       campaign_id=campaign_id)
    return {"success": True}


@router.post("/{campaign_id}/stop")
async def stop_campaign(campaign_id: str):
    """Stop a campaign and cancel pending tasks."""
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    try:
        result = await db.campaigns.update_one(
            {"_id": ObjectId(campaign_id)},
            {"$set": {"status": "stopped", "updatedAt": now, "stoppedAt": now}}
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign ID")
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Campaign not found")
    # Cancel pending tasks
    cancel_result = await db.tasks.update_many(
        {"campaignId": campaign_id, "status": {"$in": ["pending", "assigned"]}},
        {"$set": {"status": "failed", "errorMessage": "Campaign stopped", "updatedAt": now}}
    )
    await log_activity("campaign_stopped",
                       f"Campaign {campaign_id} stopped, {cancel_result.modified_count} tasks cancelled",
                       campaign_id=campaign_id, level="warning",
                       metadata={"cancelledTasks": cancel_result.modified_count})
    return {"success": True}


@router.post("/{campaign_id}/retry")
async def retry_failed_tasks(campaign_id: str):
    """Retry all failed tasks for a campaign with device shuffling.
    
    CHANGES v2:
    - Shuffles failed tasks to different devices
    - Resets retry count
    - Does NOT retry invalid_number or account_restricted
    """
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    try:
        campaign = await db.campaigns.find_one({"_id": ObjectId(campaign_id)})
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        messages = campaign.get("messages", [])
        if not messages:
            raise HTTPException(status_code=400, detail="No messages in campaign to retry with.")

        new_message = messages[0]

        # Only retry 'failed' tasks, NOT invalid_number or account_restricted
        # Reset deviceId to None so round-robin can reassign to different devices
        result = await db.tasks.update_many(
            {"campaignId": campaign_id, "status": "failed"},
            {"$set": {
                "status": "pending",
                "message": new_message,
                "updatedAt": now,
                "retryCount": 0,
                "errorMessage": None,
                "deviceId": None,  # ← Shuffle to different device
                "assignedAt": None,
            }}
        )

        # If the campaign was completed or stopped, set it back to running
        if campaign['status'] in ['completed', 'stopped']:
            await db.campaigns.update_one(
                {"_id": ObjectId(campaign_id)},
                {"$set": {"status": "running", "updatedAt": now}}
            )

        await log_activity("campaign_retried",
                           f"Retrying {result.modified_count} failed tasks for campaign {campaign_id} (shuffled to new devices)",
                           campaign_id=campaign_id,
                           metadata={"retriedTasks": result.modified_count})

        return {"success": True, "retriedTasks": result.modified_count}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{campaign_id}/report")
async def get_campaign_report(campaign_id: str):
    """Get a detailed report for a single campaign with device info."""
    db = get_db()
    try:
        # Validate campaign exists
        campaign = await db.campaigns.find_one({"_id": ObjectId(campaign_id)})
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        pipeline = [
            {"$match": {"campaignId": campaign_id}},
            {"$sort": {"updatedAt": -1}},
            {
                "$group": {
                    "_id": "$recipient",
                    "latest_task": {"$first": "$$ROOT"}
                }
            },
            {"$replaceRoot": {"newRoot": "$latest_task"}},
            {
                "$lookup": {
                    "from": "devices",
                    "localField": "deviceId",
                    "foreignField": "deviceId",
                    "as": "device_info"
                }
            },
            {
                "$addFields": {
                    "assignedDeviceId": "$deviceId",
                    "assignedDeviceName": {
                        "$ifNull": [{"$arrayElemAt": ["$device_info.deviceName", 0]}, "$deviceId"]
                    },
                    "assignedDevicePhone": {
                        "$ifNull": [{"$arrayElemAt": ["$device_info.phoneNumber", 0]}, None]
                    },
                    "failureReason": "$errorMessage"
                }
            },
            {"$project": {"device_info": 0}},
            {"$sort": {"status": 1, "updatedAt": -1}}
        ]

        tasks = await db.tasks.aggregate(pipeline).to_list(None)
        
        for task in tasks:
            task["_id"] = str(task["_id"])

        stats = {
            "total": len(tasks),
            "completed": sum(1 for t in tasks if t.get("status") == "completed"),
            "failed": sum(1 for t in tasks if t.get("status") == "failed"),
            "invalid_number": sum(1 for t in tasks if t.get("status") == "invalid_number"),
            "account_restricted": sum(1 for t in tasks if t.get("status") == "account_restricted"),
            "pending": sum(1 for t in tasks if t.get("status") in ["pending", "assigned", "in_progress"]),
        }

        return {
            "campaign": {
                "_id": str(campaign["_id"]),
                "name": campaign.get("name", ""),
                "status": campaign.get("status", ""),
                "accountType": campaign.get("accountType"),
            },
            "stats": stats,
            "tasks": tasks
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
