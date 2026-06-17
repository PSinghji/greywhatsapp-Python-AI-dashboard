"""
Inter-Device Communication API - Auto communication between non-restricted devices.
Devices chat with each other using human-like templates to maintain natural WhatsApp activity.
"""
import random
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Query
from bson import ObjectId
from app.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter()

# ─── Background Scheduler ────────────────────────────────────────────────────

_comm_task = None

async def start_device_comm_scheduler():
    """Start the background scheduler for inter-device communication."""
    global _comm_task
    if _comm_task is None or _comm_task.done():
        _comm_task = asyncio.create_task(_comm_scheduler_loop())
        logger.info("[DeviceComm] Background scheduler started")

async def _comm_scheduler_loop():
    """Background loop: every 30-90 minutes, create communication tasks between devices."""
    while True:
        try:
            wait_minutes = random.randint(30, 90)
            logger.info(f"[DeviceComm] Next communication round in {wait_minutes} minutes")
            await asyncio.sleep(wait_minutes * 60)
            await create_communication_round()
        except asyncio.CancelledError:
            logger.info("[DeviceComm] Scheduler cancelled")
            break
        except Exception as e:
            logger.error(f"[DeviceComm] Scheduler error: {e}")
            await asyncio.sleep(300)  # Wait 5 min on error


async def create_communication_round():
    """
    Create a round of inter-device communication.
    Picks random pairs of non-restricted online devices and assigns chat tasks.
    """
    db = get_db()
    if db is None:
        return

    # Get all non-restricted, active devices
    devices = await db.devices.find({
        "status": {"$nin": ["restricted", "blocked"]},
        "$or": [{"isActive": True}, {"isActive": {"$exists": False}}]
    }).to_list(100)

    if len(devices) < 2:
        logger.info("[DeviceComm] Not enough devices for communication (need at least 2)")
        return

    # Get available templates
    templates = await db.conversation_templates.find({"enabled": True}).to_list(500)
    if not templates:
        logger.warning("[DeviceComm] No conversation templates available")
        return

    # Create random pairs (each device talks to 1-2 others)
    device_list = list(devices)
    random.shuffle(device_list)
    pairs = []

    for i in range(0, len(device_list) - 1, 2):
        pairs.append((device_list[i], device_list[i + 1]))

    # If odd number, last device pairs with first
    if len(device_list) % 2 == 1 and len(device_list) > 2:
        pairs.append((device_list[-1], device_list[0]))

    now = datetime.now(timezone.utc).isoformat()
    round_id = str(ObjectId())
    tasks_created = 0

    for sender, receiver in pairs:
        # Pick a random conversation template
        template = random.choice(templates)
        messages = template.get("messages", [])

        if not messages:
            continue

        # Pick 1-3 messages from the template for this round
        msg_count = min(random.randint(1, 3), len(messages))
        selected_messages = random.sample(messages, msg_count)

        for idx, msg in enumerate(selected_messages):
            # Random delay between messages in the conversation (30s to 5min)
            delay_seconds = random.randint(30, 300) * idx

            task = {
                "type": "device_communication",
                "roundId": round_id,
                "senderId": sender.get("deviceId"),
                "senderPhone": sender.get("phoneNumber", ""),
                "senderName": sender.get("deviceName", ""),
                "receiverId": receiver.get("deviceId"),
                "receiverPhone": receiver.get("phoneNumber", ""),
                "receiverName": receiver.get("deviceName", ""),
                "message": msg.get("text", ""),
                "templateId": str(template.get("_id", "")),
                "templateName": template.get("name", ""),
                "category": template.get("category", "general"),
                "status": "pending",
                "delaySeconds": delay_seconds,
                "createdAt": now,
                "scheduledAt": (datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)).isoformat(),
                "completedAt": None,
                "error": None,
            }
            await db.device_comm_tasks.insert_one(task)
            tasks_created += 1

    # Log the round
    await db.activity_logs.insert_one({
        "eventType": "device_comm_round",
        "level": "info",
        "message": f"Communication round created: {tasks_created} messages between {len(pairs)} device pairs",
        "metadata": {"roundId": round_id, "pairs": len(pairs), "tasks": tasks_created},
        "deviceId": None,
        "campaignId": None,
        "createdAt": now,
    })

    logger.info(f"[DeviceComm] Round {round_id}: {tasks_created} tasks for {len(pairs)} pairs")
    return {"roundId": round_id, "tasksCreated": tasks_created, "pairs": len(pairs)}


# ─── API Endpoints ────────────────────────────────────────────────────────────
@router.get("/next-task")
async def get_next_comm_task(deviceId: str = Query(...)):
    """
    Get the next pending communication task for a device.
    Called by the Android agent during its heartbeat/task fetch cycle.
    """
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()

    # Find a pending task where this device is the sender and it's time to send
    task = await db.device_comm_tasks.find_one_and_update(
        {
            "senderId": deviceId,
            "status": "pending",
            "scheduledAt": {"$lte": now},
        },
        {"$set": {"status": "in_progress", "startedAt": now}},
        sort=[("scheduledAt", 1)],
    )

    if not task:
        return {"task": None}

    # Format exactly like a standard AgentTask to prevent Android Gson crashes
    receiver_phone = task.get("receiverPhone", "")
    if receiver_phone and not receiver_phone.startswith("+"):
        receiver_phone = f"+{receiver_phone}"

    return {
        "task": {
            "id": str(task["_id"]),
            "deviceId": deviceId,
            "recipient": receiver_phone,
            "accountType": "business" if "_w4b" in deviceId else "personal",
            "status": "in_progress",
            "createdAt": task.get("createdAt", now),
            "tuning": None,
            "message": {
                "type": "text",
                "content": task.get("message", ""),
                "mediaUrl": None,
                "mediaName": None,
                "caption": None,
                "mediaItems": []
            }
        }
    }

@router.post("/complete-task")
async def complete_comm_task(data: dict):
    """Mark a communication task as completed or failed."""
    db = get_db()
    task_id = data.get("taskId")
    status = data.get("status", "completed")  # completed or failed
    error = data.get("error")

    if not task_id:
        return {"error": "taskId required"}

    now = datetime.now(timezone.utc).isoformat()
    await db.device_comm_tasks.update_one(
        {"_id": ObjectId(task_id)},
        {"$set": {
            "status": status,
            "completedAt": now,
            "error": error,
        }}
    )

    return {"success": True}


@router.post("/trigger-round")
async def trigger_communication_round():
    """Manually trigger a communication round."""
    result = await create_communication_round()
    if result:
        return {"success": True, **result}
    return {"success": False, "message": "Not enough devices or templates"}


@router.get("/report")
async def communication_report(days: int = Query(30, ge=1, le=365)):
    """Get communication report for the last N days."""
    db = get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    # Overall stats
    total = await db.device_comm_tasks.count_documents({"createdAt": {"$gte": cutoff}})
    completed = await db.device_comm_tasks.count_documents({"createdAt": {"$gte": cutoff}, "status": "completed"})
    failed = await db.device_comm_tasks.count_documents({"createdAt": {"$gte": cutoff}, "status": "failed"})
    pending = await db.device_comm_tasks.count_documents({"createdAt": {"$gte": cutoff}, "status": {"$in": ["pending", "in_progress"]}})

    # Per-day breakdown
    pipeline = [
        {"$match": {"createdAt": {"$gte": cutoff}}},
        {"$addFields": {"day": {"$substr": ["$createdAt", 0, 10]}}},
        {"$group": {
            "_id": "$day",
            "total": {"$sum": 1},
            "completed": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}},
            "failed": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}},
            "uniquePairs": {"$addToSet": {"$concat": ["$senderId", "->", "$receiverId"]}},
        }},
        {"$addFields": {"pairCount": {"$size": "$uniquePairs"}}},
        {"$project": {"uniquePairs": 0}},
        {"$sort": {"_id": -1}},
    ]
    daily = await db.device_comm_tasks.aggregate(pipeline).to_list(365)
    for d in daily:
        d["date"] = d.pop("_id")

    # Per-device stats
    device_pipeline = [
        {"$match": {"createdAt": {"$gte": cutoff}}},
        {"$group": {
            "_id": "$senderId",
            "senderName": {"$first": "$senderName"},
            "senderPhone": {"$first": "$senderPhone"},
            "totalSent": {"$sum": 1},
            "completed": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}},
            "failed": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}},
            "receivers": {"$addToSet": "$receiverPhone"},
        }},
        {"$addFields": {"uniqueReceivers": {"$size": "$receivers"}}},
        {"$project": {"receivers": 0}},
        {"$sort": {"totalSent": -1}},
    ]
    device_stats = await db.device_comm_tasks.aggregate(device_pipeline).to_list(100)
    for ds in device_stats:
        ds["deviceId"] = ds.pop("_id")

    # Recent messages
    recent = await db.device_comm_tasks.find(
        {"createdAt": {"$gte": cutoff}}
    ).sort("createdAt", -1).limit(50).to_list(50)
    for r in recent:
        r["_id"] = str(r["_id"])

    return {
        "overview": {
            "total": total,
            "completed": completed,
            "failed": failed,
            "pending": pending,
            "successRate": round((completed / total * 100), 1) if total > 0 else 0,
        },
        "daily": daily,
        "deviceStats": device_stats,
        "recentMessages": recent,
    }


@router.get("/templates")
async def list_templates():
    """List all conversation templates."""
    db = get_db()
    templates = await db.conversation_templates.find({}).sort("category", 1).to_list(500)
    for t in templates:
        t["_id"] = str(t["_id"])
    return {"templates": templates}


@router.post("/templates")
async def create_template(data: dict):
    """Create a new conversation template."""
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    template = {
        "name": data.get("name", "Untitled"),
        "category": data.get("category", "general"),
        "language": data.get("language", "mixed"),
        "messages": data.get("messages", []),
        "enabled": data.get("enabled", True),
        "createdAt": now,
    }
    result = await db.conversation_templates.insert_one(template)
    return {"success": True, "id": str(result.inserted_id)}


@router.delete("/templates/{template_id}")
async def delete_template(template_id: str):
    """Delete a conversation template."""
    db = get_db()
    await db.conversation_templates.delete_one({"_id": ObjectId(template_id)})
    return {"success": True}


@router.put("/templates/{template_id}/toggle")
async def toggle_template(template_id: str):
    """Toggle a template's enabled status."""
    db = get_db()
    template = await db.conversation_templates.find_one({"_id": ObjectId(template_id)})
    if not template:
        return {"error": "Template not found"}
    new_status = not template.get("enabled", True)
    await db.conversation_templates.update_one(
        {"_id": ObjectId(template_id)},
        {"$set": {"enabled": new_status}}
    )
    return {"success": True, "enabled": new_status}
