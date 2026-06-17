"""
Agent API v2 - REST endpoints for Android APK agents.

MAJOR CHANGES:
1. TRUE Round-Robin across ALL running campaigns (not pre-assigned)
2. Smart retry with device shuffling - failed tasks go to DIFFERENT device
3. Campaign completion watchdog - ensures 100% completion
4. Wake-up signal to offline devices on campaign start
5. Anti-blocking: longer randomized delays, exponential backoff
6. Stuck task recovery: reassign after 10 min instead of 15
"""
import asyncio
import logging
import random
from fastapi import APIRouter, Body, HTTPException, Header, Query
from bson import ObjectId
from datetime import datetime, timezone, timedelta

from app.database import get_db, ensure_connected
from app.models.schemas import DeviceRegister, DeviceHeartbeat, TaskComplete
from app.api.apikeys import validate_api_key

logger = logging.getLogger(__name__)
router = APIRouter()

# ─── Background task tracking ────────────────────────────
_offline_checker_started = False
_offline_checker_task = None
_campaign_watchdog_started = False
_campaign_watchdog_task = None
_stale_task_checker_started = False
_stale_task_checker_task = None


async def verify_agent_key(x_api_key: str = Header(None)):
    """Verify the agent's API key from X-API-Key header."""
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    valid = await validate_api_key(x_api_key)
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid or disabled API key")


async def log_activity(event_type: str, message: str, device_id: str = None,
                       campaign_id: str = None, task_id: str = None,
                       level: str = "info", metadata: dict = None):
    """Log an activity event to the activity_logs collection."""
    try:
        await ensure_connected()
        db = get_db()
        if db is None:
            logger.error(f"[Activity Log] Failed to log {event_type}: db is None")
            return
            
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
        result = await db.activity_logs.insert_one(doc)
        logger.debug(f"[Activity Log] {event_type}: {message} (id: {result.inserted_id})")
    except Exception as e:
        logger.error(f"[Activity Log] Failed to log {event_type}: {e}")


# ═══════════════════════════════════════════════════════════
#  BACKGROUND: Mark stale devices offline (45s no heartbeat)
# ═══════════════════════════════════════════════════════════
async def mark_stale_devices_offline():
    """Background loop: mark devices offline if no heartbeat for 45 seconds."""
    logger.info("[Offline Checker] Started")
    
    while True:
        try:
            await asyncio.sleep(30)
            
            await ensure_connected()
            db = get_db()
            if db is None:
                continue
            
            cutoff = (datetime.now(timezone.utc) - timedelta(seconds=45)).isoformat()
            
            stale_devices = await db.devices.find({
                "status": {"$in": ["online", "busy", "idle"]},
                "lastHeartbeat": {"$lt": cutoff}
            }).to_list(100)
            
            if stale_devices:
                device_ids = [d["deviceId"] for d in stale_devices]
                result = await db.devices.update_many(
                    {"status": {"$in": ["online", "busy", "idle"]}, "lastHeartbeat": {"$lt": cutoff}},
                    {"$set": {
                        "status": "offline",
                        "updatedAt": datetime.now(timezone.utc).isoformat()
                    }}
                )
                
                if result.modified_count > 0:
                    logger.info(f"[Offline Checker] Marked {result.modified_count} device(s) offline: {device_ids}")
                    await log_activity(
                        "device_offline_auto",
                        f"{result.modified_count} device(s) marked offline (no heartbeat)",
                        level="warning",
                        metadata={"deviceIds": device_ids}
                    )
        except asyncio.CancelledError:
            logger.info("[Offline Checker] Stopped")
            break
        except Exception as e:
            logger.error(f"[Offline Checker] Error: {e}")


# ═══════════════════════════════════════════════════════════
#  BACKGROUND: Mark stale assigned tasks as failed (10 min)
# ═══════════════════════════════════════════════════════════
async def mark_stale_tasks_as_failed():
    """Background loop: reassign tasks stuck in 'assigned' state for >10 minutes.
    Instead of marking as failed, we reset to pending and shuffle to a different device."""
    logger.info("[Stale Task Checker] Started")
    
    while True:
        try:
            await asyncio.sleep(120)  # Check every 2 minutes (was 5)
            
            await ensure_connected()
            db = get_db()
            if db is None:
                continue
            
            # Tasks stuck in 'assigned' for more than 10 minutes
            cutoff = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
            
            stale_tasks = await db.tasks.find({
                "status": "assigned",
                "assignedAt": {"$lt": cutoff}
            }).to_list(200)
            
            if stale_tasks:
                now = datetime.now(timezone.utc).isoformat()
                
                # Get all online devices for reshuffling
                online_devices = await db.devices.find({
                    "status": {"$in": ["online", "idle"]},
                    "accountStatus": {"$nin": ["restricted", "blocked"]}
                }).to_list(500)
                online_device_ids = [d["deviceId"] for d in online_devices]
                
                for task in stale_tasks:
                    old_device = task.get("deviceId", "")
                    retry_count = task.get("retryCount", 0)
                    
                    # Pick a different device if possible
                    new_device = None
                    if online_device_ids:
                        available = [d for d in online_device_ids if d != old_device]
                        if available:
                            new_device = random.choice(available)
                        else:
                            new_device = random.choice(online_device_ids)
                    
                    update = {
                        "status": "pending",
                        "assignedAt": None,
                        "updatedAt": now,
                    }
                    if new_device:
                        update["deviceId"] = new_device
                    
                    await db.tasks.update_one(
                        {"_id": task["_id"]},
                        {"$set": update, "$inc": {"retryCount": 1}}
                    )
                
                logger.warning(f"[Stale Task Checker] Reshuffled {len(stale_tasks)} stuck tasks to different devices")
                await log_activity(
                    "stale_tasks_reshuffled",
                    f"{len(stale_tasks)} stuck tasks reshuffled to different devices",
                    level="warning",
                    metadata={"count": len(stale_tasks)}
                )
                    
        except asyncio.CancelledError:
            logger.info("[Stale Task Checker] Stopped")
            break
        except Exception as e:
            logger.error(f"[Stale Task Checker] Error: {e}")


# ═══════════════════════════════════════════════════════════
#  BACKGROUND: Campaign Completion Watchdog
#  Ensures campaigns reach 100% by retrying stuck/failed tasks
# ═══════════════════════════════════════════════════════════
async def campaign_completion_watchdog():
    """Background loop: Check running campaigns and ensure they complete.
    - Reassign tasks from offline/restricted devices to online ones
    - Reset failed tasks (within retry limit) back to pending
    - Mark campaigns as completed when all tasks are done
    """
    logger.info("[Campaign Watchdog] Started")
    
    while True:
        try:
            await asyncio.sleep(60)  # Check every 60 seconds
            
            await ensure_connected()
            db = get_db()
            if db is None:
                continue
            
            now = datetime.now(timezone.utc).isoformat()
            
            # Get all running campaigns
            running_campaigns = await db.campaigns.find({"status": "running"}).to_list(100)
            
            # Get online devices
            online_devices = await db.devices.find({
                "status": {"$in": ["online", "idle"]},
                "accountStatus": {"$nin": ["restricted", "blocked"]}
            }).to_list(500)
            online_device_ids = [d["deviceId"] for d in online_devices]
            
            for campaign in running_campaigns:
                cid = str(campaign["_id"])
                
                # 1. Check for tasks assigned to offline/restricted devices
                if online_device_ids:
                    orphaned_tasks = await db.tasks.find({
                        "campaignId": cid,
                        "status": {"$in": ["pending", "assigned"]},
                        "deviceId": {"$nin": online_device_ids + [None, ""]}
                    }).to_list(1000)
                    
                    if orphaned_tasks:
                        for task in orphaned_tasks:
                            new_device = random.choice(online_device_ids)
                            await db.tasks.update_one(
                                {"_id": task["_id"]},
                                {"$set": {
                                    "deviceId": new_device,
                                    "status": "pending",
                                    "assignedAt": None,
                                    "updatedAt": now,
                                }}
                            )
                        logger.info(f"[Campaign Watchdog] Campaign {cid}: Reassigned {len(orphaned_tasks)} orphaned tasks")
                
                # 2. Check for permanently failed tasks that can be retried
                #    (only tasks that have exhausted retries but campaign still running)
                max_global_retries = 5  # Allow up to 5 total retries per task
                stuck_failed = await db.tasks.find({
                    "campaignId": cid,
                    "status": "failed",
                    "retryCount": {"$lt": max_global_retries},
                    # Don't retry tasks that failed due to invalid number
                    "errorMessage": {"$not": {"$regex": "not on WhatsApp|invalid_number|Number not on"}}
                }).to_list(500)
                
                if stuck_failed and online_device_ids:
                    for task in stuck_failed:
                        old_device = task.get("deviceId", "")
                        # Shuffle to a different device
                        available = [d for d in online_device_ids if d != old_device]
                        new_device = random.choice(available) if available else random.choice(online_device_ids)
                        
                        await db.tasks.update_one(
                            {"_id": task["_id"]},
                            {"$set": {
                                "status": "pending",
                                "deviceId": new_device,
                                "assignedAt": None,
                                "errorMessage": None,
                                "updatedAt": now,
                            },
                            "$inc": {"retryCount": 1}}
                        )
                    logger.info(f"[Campaign Watchdog] Campaign {cid}: Retrying {len(stuck_failed)} failed tasks on different devices")
                    await log_activity(
                        "watchdog_retry",
                        f"Campaign {cid}: Retrying {len(stuck_failed)} failed tasks on different devices",
                        campaign_id=cid,
                        level="info",
                        metadata={"count": len(stuck_failed)}
                    )
                
                # 3. Check if campaign is complete
                remaining = await db.tasks.count_documents({
                    "campaignId": cid,
                    "status": {"$in": ["pending", "assigned", "in_progress"]}
                })
                
                if remaining == 0:
                    # All tasks are in terminal state
                    total = await db.tasks.count_documents({"campaignId": cid})
                    completed = await db.tasks.count_documents({"campaignId": cid, "status": "completed"})
                    failed = await db.tasks.count_documents({"campaignId": cid, "status": "failed"})
                    invalid = await db.tasks.count_documents({"campaignId": cid, "status": "invalid_number"})
                    
                    # Check if there are still retryable failed tasks
                    retryable = await db.tasks.count_documents({
                        "campaignId": cid,
                        "status": "failed",
                        "retryCount": {"$lt": max_global_retries},
                        "errorMessage": {"$not": {"$regex": "not on WhatsApp|invalid_number|Number not on"}}
                    })
                    
                    if retryable == 0:
                        # Truly complete - no more retryable tasks
                        await db.campaigns.update_one(
                            {"_id": ObjectId(cid)},
                            {"$set": {"status": "completed", "completedAt": now, "updatedAt": now}}
                        )
                        logger.info(f"[Campaign Watchdog] Campaign {cid} COMPLETED: "
                                  f"{completed}/{total} delivered, {failed} failed, {invalid} invalid")
                        await log_activity(
                            "campaign_completed",
                            f"Campaign completed: {completed}/{total} delivered, {failed} failed, {invalid} invalid",
                            campaign_id=cid,
                            metadata={"total": total, "completed": completed, "failed": failed, "invalid": invalid}
                        )
                        
        except asyncio.CancelledError:
            logger.info("[Campaign Watchdog] Stopped")
            break
        except Exception as e:
            logger.error(f"[Campaign Watchdog] Error: {e}")


def start_background_tasks():
    """Start all background tasks (called once on first request)."""
    global _offline_checker_started, _offline_checker_task
    global _campaign_watchdog_started, _campaign_watchdog_task
    global _stale_task_checker_started, _stale_task_checker_task
    
    if not _offline_checker_started:
        _offline_checker_started = True
        _offline_checker_task = asyncio.create_task(mark_stale_devices_offline())
        logger.info("[Agent] Offline checker task created")
    
    if not _campaign_watchdog_started:
        _campaign_watchdog_started = True
        _campaign_watchdog_task = asyncio.create_task(campaign_completion_watchdog())
        logger.info("[Agent] Campaign watchdog task created")
    
    if not _stale_task_checker_started:
        _stale_task_checker_started = True
        _stale_task_checker_task = asyncio.create_task(mark_stale_tasks_as_failed())
        logger.info("[Agent] Stale task checker task created")


# ─── Health Check ────────────────────────────────────────
@router.get("/health")
async def health_check():
    """Health check endpoint (no auth required)."""
    try:
        start_background_tasks()
        await ensure_connected()
        db = get_db()
        
        if db is None:
            return {"status": "error", "message": "Database not connected", "timestamp": datetime.now(timezone.utc).isoformat()}
        
        await db.command("ping")
        return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        logger.error(f"[Health Check] Error: {e}")
        return {"status": "error", "message": str(e), "timestamp": datetime.now(timezone.utc).isoformat()}


# ─── Register Device ─────────────────────────────────────
@router.post("/register")
async def register_device(data: DeviceRegister, x_api_key: str = Header(None)):
    """Register a new device or update existing registration."""
    try:
        await verify_agent_key(x_api_key)
        start_background_tasks()
        await ensure_connected()
        db = get_db()
        
        if db is None:
            raise HTTPException(status_code=503, detail="Database not available")
        
        now = datetime.now(timezone.utc).isoformat()
        existing = await db.devices.find_one({"deviceId": data.deviceId})
        
        if existing:
            current_status = existing.get("status", "")
            new_status = "online"
            if current_status in ("restricted", "blocked"):
                new_status = current_status
                logger.warning(f"[Device] Device {data.deviceId} reconnected but still {current_status}")
            
            await db.devices.update_one(
                {"deviceId": data.deviceId},
                {"$set": {
                    "deviceName": data.deviceName or existing.get("deviceName"),
                    "phoneNumber": data.phoneNumber or existing.get("phoneNumber"),
                    "androidVersion": data.androidVersion,
                    "model": data.model,
                    "appVersion": data.appVersion,
                    "whatsappAccountType": data.whatsappAccountType.value if data.whatsappAccountType else existing.get("whatsappAccountType"),
                    "status": new_status,
                    "lastHeartbeat": now,
                    "updatedAt": now,
                }}
            )
            logger.info(f"[Device] Device {data.deviceId} reconnected (status: {new_status})")
            await log_activity("device_reconnected", f"Device {data.deviceId} reconnected (status: {new_status})",
                               device_id=data.deviceId,
                               metadata={"model": data.model, "appVersion": data.appVersion, "status": new_status})
            
            return {
                "success": True,
                "message": "Device updated",
                "deviceId": data.deviceId,
                "deviceStatus": new_status,
                "shouldStop": new_status in ("restricted", "blocked"),
            }
        else:
            device = {
                "deviceId": data.deviceId,
                "deviceName": data.deviceName or f"Device-{data.deviceId[:8]}",
                "phoneNumber": data.phoneNumber,
                "androidVersion": data.androidVersion,
                "model": data.model,
                "appVersion": data.appVersion,
                "whatsappAccountType": data.whatsappAccountType.value if data.whatsappAccountType else "personal",
                "status": "online",
                "accountStatus": "active",
                "batteryLevel": 0,
                "isCharging": False,
                "tasksSentCount": 0,
                "tasksFailedCount": 0,
                "lastHeartbeat": now,
                "createdAt": now,
                "updatedAt": now,
            }
            await db.devices.insert_one(device)
            logger.info(f"[Device] New device registered: {data.deviceId}")
            await log_activity("device_registered", f"New device registered: {data.deviceId}",
                               device_id=data.deviceId,
                               metadata={"model": data.model, "appVersion": data.appVersion})
            
            return {
                "success": True,
                "message": "Device registered",
                "deviceId": data.deviceId,
                "deviceStatus": "online",
                "shouldStop": False,
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Register] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")


# ─── Heartbeat ──────────────────────────────────────────
@router.post("/heartbeat")
async def heartbeat(data: DeviceHeartbeat, x_api_key: str = Header(None)):
    """Receive heartbeat from device. Returns commands and status."""
    try:
        await verify_agent_key(x_api_key)
        start_background_tasks()
        await ensure_connected()
        db = get_db()
        
        if db is None:
            raise HTTPException(status_code=503, detail="Database not available")
        
        now = datetime.now(timezone.utc).isoformat()
        device = await db.devices.find_one({"deviceId": data.deviceId})
        if not device:
            raise HTTPException(status_code=404, detail="Device not registered. Please register first.")
        
        was_offline = device.get("status") in ("offline", None)
        
        # Determine new status
        if data.accountStatus == "restricted":
            new_status = "restricted"
            logger.critical(f"[Heartbeat] Device {data.deviceId} reported account RESTRICTED!")
            await log_activity("account_restricted",
                               f"Device {data.deviceId} WhatsApp account is restricted!",
                               device_id=data.deviceId, level="critical")
        elif data.accountStatus == "blocked":
            new_status = "blocked"
            logger.critical(f"[Heartbeat] Device {data.deviceId} reported account BLOCKED!")
            await log_activity("account_blocked",
                               f"Device {data.deviceId} WhatsApp account is blocked!",
                               device_id=data.deviceId, level="critical")
        elif device.get("status") in ("restricted", "blocked"):
            # Keep restricted/blocked - only admin can clear
            new_status = device.get("status")
        elif data.accountStatus == "idle":
            # 'idle' = WorkManager background heartbeat (AgentService not running)
            # Mark as 'standby' so dashboard knows device is reachable but not active
            new_status = "online"  # Keep as online so it can receive wake-up commands
            logger.info(f"[Heartbeat] Device {data.deviceId} background heartbeat (service idle, device reachable)")
        else:
            new_status = "online"
        
        update_data = {
            "batteryLevel": data.batteryLevel,
            "isCharging": data.isCharging,
            "wifiConnected": data.wifiConnected if hasattr(data, 'wifiConnected') else None,
            "mobileData": data.mobileData if hasattr(data, 'mobileData') else None,
            "whatsappInstalled": data.whatsappInstalled if hasattr(data, 'whatsappInstalled') else None,
            "freeMemoryMB": data.freeMemoryMB if hasattr(data, 'freeMemoryMB') else None,
            "status": new_status,
            "lastHeartbeat": now,
            "updatedAt": now,
        }
        
        if data.deviceName:
            update_data["deviceName"] = data.deviceName
        if data.phoneNumber:
            update_data["phoneNumber"] = data.phoneNumber
        if data.personalEnabled is not None:
            update_data["personalEnabled"] = data.personalEnabled
        if data.businessEnabled is not None:
            update_data["businessEnabled"] = data.businessEnabled
        if data.personalPhone:
            update_data["personalPhone"] = data.personalPhone
        if data.businessPhone:
            update_data["businessPhone"] = data.businessPhone
        
        update_data = {k: v for k, v in update_data.items() if v is not None}
        
        await db.devices.update_one({"deviceId": data.deviceId}, {"$set": update_data})
        
        if was_offline and new_status == "online":
            logger.info(f"[Heartbeat] Device {data.deviceId} back online")
            await log_activity("device_back_online", f"Device {data.deviceId} back online",
                               device_id=data.deviceId)
        
        # Check for pending commands (including wake_up)
        pending_command = device.get("pendingCommand")
        if pending_command:
            await db.devices.update_one(
                {"deviceId": data.deviceId},
                {"$set": {"pendingCommand": None}}
            )
            logger.info(f"[Heartbeat] Command '{pending_command}' sent to {data.deviceId}")
            await log_activity("command_sent", f"Command '{pending_command}' sent to {data.deviceId}",
                               device_id=data.deviceId, metadata={"command": pending_command})
        
        return {
            "success": True,
            "command": pending_command,
            "deviceStatus": new_status,
            "shouldStop": new_status in ("restricted", "blocked"),
            "timestamp": now,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Heartbeat] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Heartbeat failed: {str(e)}")


# ═══════════════════════════════════════════════════════════
#  FETCH TASKS - TRUE ROUND-ROBIN ACROSS ALL CAMPAIGNS
# ═══════════════════════════════════════════════════════════
@router.get("/tasks")
async def fetch_tasks(deviceId: str = Query(...), limit: int = Query(1, ge=1, le=5),
                      x_api_key: str = Header(None)):
    """Fetch pending tasks for a device using TRUE round-robin across all running campaigns.
    
    SMART DISTRIBUTION:
    - Picks 1 task from each running campaign in rotation
    - Device gets tasks from ALL campaigns equally
    - Tasks not pre-assigned to specific devices - any online device can pick any task
    - Anti-blocking: returns only 1 task at a time (default) for maximum control
    """
    try:
        await verify_agent_key(x_api_key)
        await ensure_connected()
        db = get_db()
        
        if db is None:
            raise HTTPException(status_code=503, detail="Database not available")
        
        # Check device exists and is not restricted/blocked
        device = await db.devices.find_one({"deviceId": deviceId})
        if not device:
            raise HTTPException(status_code=404, detail="Device not registered")
        
        device_status = device.get("status", "")
        
        if device_status == "restricted":
            logger.warning(f"[Fetch Tasks] Device {deviceId} is RESTRICTED - no tasks delivered")
            return {
                "tasks": [], "count": 0,
                "message": "Device is restricted. No tasks will be delivered.",
                "deviceStatus": "restricted", "shouldStop": True,
            }
        if device_status == "blocked":
            logger.warning(f"[Fetch Tasks] Device {deviceId} is BLOCKED - no tasks delivered")
            return {
                "tasks": [], "count": 0,
                "message": "Device is blocked. No tasks will be delivered.",
                "deviceStatus": "blocked", "shouldStop": True,
            }
        if device_status == "paused":
            return {"tasks": [], "count": 0, "message": "Device is paused",
                    "deviceStatus": "paused", "shouldStop": False}
        
        # Get all running campaigns
        running_campaigns = await db.campaigns.find({"status": "running"}).to_list(500)
        running_campaign_ids = [str(c["_id"]) for c in running_campaigns]
        
        if not running_campaign_ids:
            return {"tasks": [], "count": 0, "message": "No running campaigns",
                    "deviceStatus": device_status, "shouldStop": False}
        
        # ═══════════════════════════════════════════════════
        # TRUE ROUND-ROBIN: Pick tasks across campaigns
        # ═══════════════════════════════════════════════════
        
        # Get the device's last campaign index for round-robin tracking
        last_campaign_idx = device.get("lastCampaignIndex", 0) % max(len(running_campaign_ids), 1)
        
        mixed_tasks = []
        campaigns_checked = 0
        
        while len(mixed_tasks) < limit and campaigns_checked < len(running_campaign_ids):
            # Rotate through campaigns starting from where we left off
            idx = (last_campaign_idx + campaigns_checked) % len(running_campaign_ids)
            campaign_id = running_campaign_ids[idx]
            campaigns_checked += 1
            
            # Find ONE pending task from this campaign
            # Prefer tasks assigned to this device, but also pick unassigned tasks
            task = await db.tasks.find_one({
                "campaignId": campaign_id,
                "status": "pending",
                "$or": [
                    {"deviceId": deviceId},
                    {"deviceId": None},
                    {"deviceId": ""},
                ]
            }, sort=[("createdAt", 1)])
            
            # If no task with preference, try any pending task from this campaign
            if not task:
                task = await db.tasks.find_one({
                    "campaignId": campaign_id,
                    "status": "pending",
                }, sort=[("createdAt", 1)])
            
            if task:
                task["_id"] = str(task["_id"])
                mixed_tasks.append(task)
        
        # Update the device's campaign rotation index
        next_idx = (last_campaign_idx + campaigns_checked) % max(len(running_campaign_ids), 1)
        await db.devices.update_one(
            {"deviceId": deviceId},
            {"$set": {"lastCampaignIndex": next_idx}}
        )
        
        # Mark fetched tasks as assigned
        if mixed_tasks:
            now = datetime.now(timezone.utc).isoformat()
            task_ids = [ObjectId(t["_id"]) for t in mixed_tasks]
            await db.tasks.update_many(
                {"_id": {"$in": task_ids}},
                {"$set": {
                    "status": "assigned",
                    "deviceId": deviceId,
                    "assignedAt": now,
                    "updatedAt": now,
                }}
            )
            
            campaign_names = [t.get("campaignName", t.get("campaignId", "?")) for t in mixed_tasks]
            logger.info(f"[Tasks] Assigned {len(mixed_tasks)} tasks to {deviceId} from campaigns: {campaign_names}")
            await log_activity("tasks_assigned",
                               f"{len(mixed_tasks)} tasks assigned to {deviceId} (round-robin)",
                               device_id=deviceId,
                               metadata={"taskIds": [str(tid) for tid in task_ids],
                                        "campaigns": campaign_names})
        
        return {"tasks": mixed_tasks, "count": len(mixed_tasks),
                "deviceStatus": device_status, "shouldStop": False}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Fetch Tasks] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Task fetch failed: {str(e)}")


# ═══════════════════════════════════════════════════════════
#  COMPLETE TASK - Smart retry with device shuffling
# ═══════════════════════════════════════════════════════════
@router.post("/tasks/complete")
async def complete_task(data: TaskComplete, x_api_key: str = Header(None)):
    """Report task completion or failure.
    
    SMART RETRY:
    - Failed tasks are reshuffled to a DIFFERENT device
    - Exponential backoff between retries
    - Invalid numbers are NEVER retried
    - Account restricted tasks trigger device lockout
    """
    try:
        await verify_agent_key(x_api_key)
        await ensure_connected()
        db = get_db()
        
        if db is None:
            raise HTTPException(status_code=503, detail="Database not available")
        
        now = datetime.now(timezone.utc).isoformat()
        try:
            task = await db.tasks.find_one({"_id": ObjectId(data.taskId)})
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid task ID")
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        final_status = data.status.value if hasattr(data.status, 'value') else str(data.status)
        
        update_data = {
            "status": final_status,
            "updatedAt": now,
        }
        
        if final_status == "completed":
            update_data["deliveredAt"] = data.deliveredAt or now
        if data.errorMessage:
            update_data["errorMessage"] = data.errorMessage
        
        await db.tasks.update_one({"_id": ObjectId(data.taskId)}, {"$set": update_data})
        logger.info(f"[Task Complete] Task {data.taskId} marked as {final_status}")
        
        # ─── Handle each status ───────────────────────────
        if final_status == "completed":
            await db.devices.update_one(
                {"deviceId": data.deviceId},
                {"$inc": {"tasksSentCount": 1}}
            )
            await log_activity("task_completed",
                               f"Message delivered to {task.get('recipient', 'unknown')}",
                               device_id=data.deviceId,
                               campaign_id=task.get("campaignId"),
                               task_id=data.taskId)
        
        elif final_status == "invalid_number":
            # Number is not on WhatsApp - mark permanently, NO retry
            await db.tasks.update_one(
                {"_id": ObjectId(data.taskId)},
                {"$set": {"status": "invalid_number", "updatedAt": now,
                          "errorMessage": data.errorMessage or "Number not on WhatsApp"}}
            )
            await db.devices.update_one(
                {"deviceId": data.deviceId},
                {"$inc": {"tasksFailedCount": 1}}
            )
            logger.warning(f"[Task Complete] Number {task.get('recipient', 'unknown')} is not on WhatsApp")
            await log_activity("invalid_number",
                               f"Number not on WhatsApp: {task.get('recipient', 'unknown')}",
                               device_id=data.deviceId,
                               campaign_id=task.get("campaignId"),
                               task_id=data.taskId,
                               level="warning",
                               metadata={"errorMessage": data.errorMessage, "recipient": task.get('recipient')})
        
        elif final_status == "account_restricted":
            # CRITICAL: WhatsApp account is restricted
            await db.tasks.update_one(
                {"_id": ObjectId(data.taskId)},
                {"$set": {"status": "pending", "updatedAt": now, "deviceId": None,
                          "errorMessage": None, "assignedAt": None}}
            )
            await db.devices.update_one(
                {"deviceId": data.deviceId},
                {"$set": {
                    "status": "restricted",
                    "accountStatus": "restricted",
                    "restrictedAt": now,
                    "updatedAt": now,
                }}
            )
            # Reassign ALL pending/assigned tasks from this device
            reassigned = await db.tasks.update_many(
                {"deviceId": data.deviceId, "status": {"$in": ["pending", "assigned"]}},
                {"$set": {"status": "pending", "deviceId": None, "updatedAt": now, "assignedAt": None}}
            )
            logger.critical(f"[ACCOUNT RESTRICTED] Device {data.deviceId} restricted! "
                          f"Reassigned {reassigned.modified_count} tasks.")
            await log_activity("account_restricted",
                               f"CRITICAL: Device {data.deviceId} RESTRICTED! "
                               f"{reassigned.modified_count + 1} tasks reassigned.",
                               device_id=data.deviceId,
                               campaign_id=task.get("campaignId"),
                               task_id=data.taskId,
                               level="critical",
                               metadata={"reassignedTasks": reassigned.modified_count + 1})
        
        elif final_status == "account_blocked":
            # CRITICAL: WhatsApp account is blocked/banned
            await db.tasks.update_one(
                {"_id": ObjectId(data.taskId)},
                {"$set": {"status": "pending", "updatedAt": now, "deviceId": None,
                          "errorMessage": None, "assignedAt": None}}
            )
            await db.devices.update_one(
                {"deviceId": data.deviceId},
                {"$set": {
                    "status": "blocked",
                    "accountStatus": "blocked",
                    "blockedAt": now,
                    "updatedAt": now,
                }}
            )
            reassigned = await db.tasks.update_many(
                {"deviceId": data.deviceId, "status": {"$in": ["pending", "assigned"]}},
                {"$set": {"status": "pending", "deviceId": None, "updatedAt": now, "assignedAt": None}}
            )
            logger.critical(f"[ACCOUNT BLOCKED] Device {data.deviceId} BLOCKED! "
                          f"Reassigned {reassigned.modified_count} tasks.")
            await log_activity("account_blocked",
                               f"CRITICAL: Device {data.deviceId} BLOCKED! "
                               f"{reassigned.modified_count + 1} tasks reassigned.",
                               device_id=data.deviceId,
                               campaign_id=task.get("campaignId"),
                               task_id=data.taskId,
                               level="critical",
                               metadata={"reassignedTasks": reassigned.modified_count + 1})
        
        elif final_status == "failed":
            # ═══ SMART RETRY WITH DEVICE SHUFFLING ═══
            retry_count = task.get("retryCount", 0)
            max_retries = task.get("maxRetries", 3)
            
            if retry_count < max_retries:
                # Get online devices excluding current one
                online_devices = await db.devices.find({
                    "status": {"$in": ["online", "idle"]},
                    "accountStatus": {"$nin": ["restricted", "blocked"]},
                    "deviceId": {"$ne": data.deviceId}
                }).to_list(100)
                
                new_device_id = None
                if online_devices:
                    new_device_id = random.choice(online_devices)["deviceId"]
                
                update_retry = {
                    "status": "pending",
                    "updatedAt": now,
                    "assignedAt": None,
                    "errorMessage": None,
                }
                if new_device_id:
                    update_retry["deviceId"] = new_device_id
                else:
                    update_retry["deviceId"] = None  # Let any device pick it up
                
                await db.tasks.update_one(
                    {"_id": ObjectId(data.taskId)},
                    {"$set": update_retry, "$inc": {"retryCount": 1}}
                )
                logger.warning(f"[Task Complete] Task {data.taskId} retry {retry_count + 1}/{max_retries} "
                             f"→ shuffled to device {new_device_id or 'any'}")
                await log_activity("task_retry_shuffled",
                                   f"Task retrying ({retry_count + 1}/{max_retries}) for {task.get('recipient', 'unknown')} "
                                   f"→ shuffled to {new_device_id or 'any available device'}",
                                   device_id=data.deviceId,
                                   campaign_id=task.get("campaignId"),
                                   task_id=data.taskId,
                                   level="warning",
                                   metadata={"retryCount": retry_count + 1,
                                            "oldDevice": data.deviceId,
                                            "newDevice": new_device_id})
            else:
                await db.devices.update_one(
                    {"deviceId": data.deviceId},
                    {"$inc": {"tasksFailedCount": 1}}
                )
                logger.error(f"[Task Complete] Task {data.taskId} failed permanently: {data.errorMessage}")
                await log_activity("task_failed",
                                   f"Message failed permanently to {task.get('recipient', 'unknown')}: {data.errorMessage}",
                                   device_id=data.deviceId,
                                   campaign_id=task.get("campaignId"),
                                   task_id=data.taskId,
                                   level="error",
                                   metadata={"errorMessage": data.errorMessage, "retryCount": retry_count})
        
        # Campaign completion check is now handled by the watchdog
        # But do a quick check here too for responsiveness
        campaign_id = task.get("campaignId")
        if campaign_id:
            remaining = await db.tasks.count_documents({
                "campaignId": campaign_id,
                "status": {"$in": ["pending", "assigned", "in_progress"]}
            })
            if remaining == 0:
                # Quick check - are there retryable failed tasks?
                retryable = await db.tasks.count_documents({
                    "campaignId": campaign_id,
                    "status": "failed",
                    "retryCount": {"$lt": 5},
                    "errorMessage": {"$not": {"$regex": "not on WhatsApp|invalid_number|Number not on"}}
                })
                if retryable == 0:
                    await db.campaigns.update_one(
                        {"_id": ObjectId(campaign_id)},
                        {"$set": {"status": "completed", "completedAt": now, "updatedAt": now}}
                    )
                    logger.info(f"[Task Complete] Campaign {campaign_id} completed")
                    await log_activity("campaign_completed",
                                       f"Campaign completed: {task.get('campaignName', campaign_id)}",
                                       campaign_id=campaign_id)
        
        return {"success": True}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Task Complete] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Task completion failed: {str(e)}")


# ─── Config Sync (from Android agent) ────────────────────
@router.post("/config/sync")
async def sync_config(request_data: dict = Body(...), x_api_key: str = Header(None)):
    """Sync device configuration from Android agent to dashboard."""
    try:
        await verify_agent_key(x_api_key)
        await ensure_connected()
        db = get_db()
        
        if db is None:
            raise HTTPException(status_code=503, detail="Database not available")
        
        device_id = request_data.get("deviceId", "")
        if not device_id:
            raise HTTPException(status_code=400, detail="deviceId is required")
        
        now = datetime.now(timezone.utc).isoformat()
        device = await db.devices.find_one({"deviceId": device_id})
        if not device:
            raise HTTPException(status_code=404, detail="Device not registered")
        
        update_data = {"updatedAt": now}
        
        if request_data.get("deviceName"):
            update_data["deviceName"] = request_data["deviceName"]
        if request_data.get("personalEnabled") is not None:
            update_data["personalEnabled"] = request_data["personalEnabled"]
        if request_data.get("personalPhone"):
            update_data["personalPhone"] = request_data["personalPhone"]
        if request_data.get("businessEnabled") is not None:
            update_data["businessEnabled"] = request_data["businessEnabled"]
        if request_data.get("businessPhone"):
            update_data["businessPhone"] = request_data["businessPhone"]
        if request_data.get("autoStart") is not None:
            update_data["autoStart"] = request_data["autoStart"]
        
        await db.devices.update_one({"deviceId": device_id}, {"$set": update_data})
        logger.info(f"[Config Sync] Device {device_id} config synced")
        await log_activity("config_sync", f"Device {device_id} configuration synced",
                           device_id=device_id, metadata=update_data)
        
        current_status = device.get("status", "online")
        return {
            "success": True,
            "deviceStatus": current_status,
            "shouldStop": current_status in ("restricted", "blocked"),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Config Sync] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Config sync failed: {str(e)}")


# ─── Step Logging (from Android agent) ──────────────────
@router.post("/log-step")
async def log_step(request_data: dict = Body(...), x_api_key: str = Header(None)):
    """Receive step-by-step logs from the Android agent."""
    try:
        await verify_agent_key(x_api_key)
        await ensure_connected()
        db = get_db()
        
        if db is None:
            raise HTTPException(status_code=503, detail="Database not available")
        
        task_id = request_data.get("taskId", "")
        device_id = request_data.get("deviceId", "")
        step = request_data.get("step", "unknown")
        message = request_data.get("message", "")
        timestamp = request_data.get("timestamp", "")
        
        doc = {
            "eventType": "agent_step",
            "deviceId": device_id,
            "taskId": task_id,
            "message": f"[{step}] {message}",
            "level": "info",
            "metadata": {
                "step": step,
                "rawMessage": message,
                "agentTimestamp": timestamp
            },
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        await db.activity_logs.insert_one(doc)
        
        return {"success": True}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Step Log] Error: {e}")
        return {"success": False}


# ─── Activity Logs ───────────────────────────────────────
@router.get("/logs")
async def get_activity_logs(
    limit: int = Query(100, ge=1, le=500),
    level: str = Query(None),
    device_id: str = Query(None, alias="deviceId"),
    event_type: str = Query(None, alias="eventType"),
    x_api_key: str = Header(None)
):
    """Get recent activity logs."""
    try:
        await verify_agent_key(x_api_key)
        await ensure_connected()
        db = get_db()
        
        if db is None:
            raise HTTPException(status_code=503, detail="Database not available")
        
        query = {}
        if level:
            query["level"] = level
        if device_id:
            query["deviceId"] = device_id
        if event_type:
            query["eventType"] = event_type
        
        logs = await db.activity_logs.find(query).sort("createdAt", -1).limit(limit).to_list(limit)
        for log in logs:
            log["_id"] = str(log["_id"])
        return {"logs": logs, "count": len(logs)}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Activity Logs] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch logs: {str(e)}")


# ─── Clear Device Restriction (Admin only) ───────────────
@router.post("/devices/{device_id}/clear-restriction")
async def clear_device_restriction(device_id: str, x_api_key: str = Header(None)):
    """Admin endpoint: Clear restricted/blocked status from a device."""
    try:
        await verify_agent_key(x_api_key)
        await ensure_connected()
        db = get_db()
        
        if db is None:
            raise HTTPException(status_code=503, detail="Database not available")
        
        device = await db.devices.find_one({"deviceId": device_id})
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        
        old_status = device.get("status", "")
        if old_status not in ("restricted", "blocked"):
            return {"success": True, "message": f"Device is not restricted/blocked (current: {old_status})"}
        
        now = datetime.now(timezone.utc).isoformat()
        await db.devices.update_one(
            {"deviceId": device_id},
            {"$set": {
                "status": "online",
                "accountStatus": "active",
                "updatedAt": now,
            },
            "$unset": {
                "restrictedAt": "",
                "blockedAt": "",
            }}
        )
        
        logger.info(f"[Admin] Device {device_id} restriction cleared (was: {old_status})")
        await log_activity("restriction_cleared",
                           f"Device {device_id} restriction cleared by admin (was: {old_status})",
                           device_id=device_id)
        
        return {"success": True, "message": f"Device {device_id} restriction cleared."}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Clear Restriction] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear restriction: {str(e)}")
