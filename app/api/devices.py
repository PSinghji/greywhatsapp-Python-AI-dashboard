"""
Devices API - Manage connected Android agents.
"""
from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone

from app.models.schemas import DeviceUpdate
from app.services.device_service import DeviceService

router = APIRouter()
device_service = DeviceService()

def serialize_device(doc):
    """Convert MongoDB document to JSON-serializable dict."""
    if doc is None:
        return None
    doc["_id"] = str(doc["_id"])
    return doc


@router.get("")
async def list_devices():
    """List all registered devices."""
    devices = await device_service.get_all_devices()
    return [serialize_device(d) for d in devices]


@router.get("/stats")
async def device_stats():
    """Get device statistics."""
    # Logic moved to service: This now executes 1 fast aggregation query 
    # instead of 6 slow count_documents queries.
    return await device_service.get_device_stats()


@router.get("/{device_id}")
async def get_device(device_id: str):
    """Get a single device by its deviceId."""
    device = await device_service.get_device_by_id(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return serialize_device(device)


@router.put("/{device_id}")
async def update_device(device_id: str, data: DeviceUpdate):
    """Update device name, phone, or status."""
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    result = await device_service.update_device(device_id, update_data)
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"success": True, "message": "Device updated"}


@router.delete("/{device_id}")
async def delete_device(device_id: str):
    """Remove a device from the system."""
    result = await device_service.delete_device(device_id)
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"success": True, "message": "Device removed"}


@router.post("/{device_id}/command")
async def send_command(device_id: str, command: dict):
    """Send a command to a device (pause, resume, stop, wake_up)."""
    valid_commands = ["pause", "resume", "stop", "restart", "wake_up"]
    cmd = command.get("command")
    if cmd not in valid_commands:
        raise HTTPException(status_code=400, detail=f"Invalid command. Use: {valid_commands}")

    device = await device_service.get_device_by_id(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    await device_service.queue_command(device_id, cmd)
    return {"success": True, "message": f"Command '{cmd}' queued for device"}


@router.post("/wake-all")
async def wake_all_devices():
    """
    Send wake_up command to ALL non-restricted devices.
    This sets pendingCommand='wake_up' so when the HeartbeatWorker
    (running every 15 min even when app is killed) sends its next
    heartbeat, it will receive the wake_up command and restart AgentService.
    """
    target_devices = await device_service.get_target_devices()

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

        # Set wake_up command for offline/paused/error devices using the service
        await device_service.queue_command(device_id, "wake_up")
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