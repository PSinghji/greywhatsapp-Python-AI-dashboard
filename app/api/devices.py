"""
Devices API - Manage connected Android agents.
"""
from fastapi import APIRouter, HTTPException
from bson import ObjectId
from datetime import datetime, timezone

from app.database import get_db
from app.models.schemas import DeviceRegister, DeviceUpdate

router = APIRouter()


def serialize_device(doc):
    """Convert MongoDB document to JSON-serializable dict."""
    if doc is None:
        return None
    doc["_id"] = str(doc["_id"])
    return doc


@router.get("")
async def list_devices():
    """List all registered devices."""
    db = get_db()
    devices = await db.devices.find().sort("lastHeartbeat", -1).to_list(500)
    return [serialize_device(d) for d in devices]


@router.get("/stats")
async def device_stats():
    """Get device statistics."""
    db = get_db()
    total = await db.devices.count_documents({})
    online = await db.devices.count_documents({"status": "online"})
    offline = await db.devices.count_documents({"status": "offline"})
    error = await db.devices.count_documents({"status": "error"})
    paused = await db.devices.count_documents({"status": "paused"})
    restricted = await db.devices.count_documents({"status": "restricted"})
    return {
        "total": total,
        "online": online,
        "offline": offline,
        "error": error,
        "paused": paused,
        "restricted": restricted,
    }


@router.get("/{device_id}")
async def get_device(device_id: str):
    """Get a single device by its deviceId."""
    db = get_db()
    device = await db.devices.find_one({"deviceId": device_id})
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return serialize_device(device)


@router.put("/{device_id}")
async def update_device(device_id: str, data: DeviceUpdate):
    """Update device name, phone, or status."""
    db = get_db()
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    update_data["updatedAt"] = datetime.now(timezone.utc).isoformat()
    result = await db.devices.update_one(
        {"deviceId": device_id}, {"$set": update_data}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"success": True, "message": "Device updated"}


@router.delete("/{device_id}")
async def delete_device(device_id: str):
    """Remove a device from the system."""
    db = get_db()
    result = await db.devices.delete_one({"deviceId": device_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Device not found")
    # Also remove pending tasks for this device
    await db.tasks.delete_many({"deviceId": device_id, "status": {"$in": ["pending", "assigned"]}})
    return {"success": True, "message": "Device removed"}


@router.post("/{device_id}/command")
async def send_command(device_id: str, command: dict):
    """Send a command to a device (pause, resume, stop, wake_up)."""
    db = get_db()
    valid_commands = ["pause", "resume", "stop", "restart", "wake_up"]
    cmd = command.get("command")
    if cmd not in valid_commands:
        raise HTTPException(status_code=400, detail=f"Invalid command. Use: {valid_commands}")

    device = await db.devices.find_one({"deviceId": device_id})
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    await db.devices.update_one(
        {"deviceId": device_id},
        {"$set": {"pendingCommand": cmd, "commandAt": datetime.now(timezone.utc).isoformat()}}
    )
    return {"success": True, "message": f"Command '{cmd}' queued for device"}


@router.post("/wake-all")
async def wake_all_devices():
    """
    Send wake_up command to ALL non-restricted devices.
    This sets pendingCommand='wake_up' so when the HeartbeatWorker
    (running every 15 min even when app is killed) sends its next
    heartbeat, it will receive the wake_up command and restart AgentService.
    """
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()

    # Find all devices that are not restricted/blocked
    target_devices = await db.devices.find(
        {"status": {"$nin": ["restricted", "blocked"]}}
    ).to_list(500)

    if not target_devices:
        return {"success": True, "woken": 0, "message": "No eligible devices found"}

    woken_count = 0
    woken_devices = []
    already_online = 0

    for device in target_devices:
        device_id = device["deviceId"]
        status = device.get("status", "offline")

        if status == "online":
            already_online += 1
            continue

        # Set wake_up command for offline/paused/error devices
        await db.devices.update_one(
            {"deviceId": device_id},
            {"$set": {
                "pendingCommand": "wake_up",
                "commandAt": now
            }}
        )
        woken_count += 1
        woken_devices.append(device.get("deviceName", device_id[:12]))

    # Log the wake-all action
    from app.api.logs import log_activity
    await log_activity(
        level="info",
        event="wake_all_devices",
        message=f"Wake-up sent to {woken_count} offline devices. {already_online} already online.",
        metadata={
            "woken_count": woken_count,
            "already_online": already_online,
            "woken_devices": woken_devices[:20]  # limit log size
        }
    )

    return {
        "success": True,
        "woken": woken_count,
        "already_online": already_online,
        "total": len(target_devices),
        "message": f"Wake-up command sent to {woken_count} devices. {already_online} already online."
    }
