"""
Agent API v2 - REST endpoints for Android APK agents.
"""
import asyncio
import logging
from fastapi import APIRouter, Body, HTTPException, Header, Query
from datetime import datetime, timezone

from app.database import ensure_connected
from app.models.schemas import DeviceRegister, DeviceHeartbeat, TaskComplete
from app.api.apikeys import validate_api_key
from app.services.agent_service import AgentService

logger = logging.getLogger(__name__)
router = APIRouter()
agent_service = AgentService()

# ─── Background task tracking ────────────────────────────
_tasks_started = False

async def verify_agent_key(x_api_key: str = Header(None)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    if not await validate_api_key(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid or disabled API key")

# ─── BACKGROUND LOOPS ────────────────────────────────────
async def mark_stale_devices_offline():
    while True:
        try:
            await asyncio.sleep(30)
            await ensure_connected()
            if agent_service.db is not None:
                await agent_service.check_offline_devices()
        except asyncio.CancelledError: break
        except Exception as e: logger.error(f"[Offline Checker] Error: {e}")

async def mark_stale_tasks_as_failed():
    while True:
        try:
            await asyncio.sleep(120)
            await ensure_connected()
            if agent_service.db is not None:
                await agent_service.check_stale_tasks()
        except asyncio.CancelledError: break
        except Exception as e: logger.error(f"[Stale Task Checker] Error: {e}")

async def campaign_completion_watchdog():
    while True:
        try:
            await asyncio.sleep(60)
            await ensure_connected()
            if agent_service.db is not None:
                await agent_service.run_campaign_watchdog()
        except asyncio.CancelledError: break
        except Exception as e: logger.error(f"[Campaign Watchdog] Error: {e}")

def start_background_tasks():
    global _tasks_started
    if not _tasks_started:
        _tasks_started = True
        asyncio.create_task(mark_stale_devices_offline())
        asyncio.create_task(mark_stale_tasks_as_failed())
        asyncio.create_task(campaign_completion_watchdog())
        logger.info("[Agent] Background tasks started")

# ─── API ENDPOINTS ───────────────────────────────────────

@router.get("/health")
async def health_check():
    try:
        start_background_tasks()
        await ensure_connected()
        if agent_service.db is None: return {"status": "error", "message": "No DB"}
        await agent_service.db.command("ping")
        return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.post("/register")
async def register_device(data: DeviceRegister, x_api_key: str = Header(None)):
    await verify_agent_key(x_api_key)
    start_background_tasks()
    await ensure_connected()
    return await agent_service.register_device(data.model_dump())

@router.post("/heartbeat")
async def heartbeat(data: DeviceHeartbeat, x_api_key: str = Header(None)):
    await verify_agent_key(x_api_key)
    start_background_tasks()
    await ensure_connected()
    result = await agent_service.process_heartbeat(data.model_dump())
    if not result:
        raise HTTPException(status_code=404, detail="Device not registered.")
    return result

@router.get("/tasks")
async def fetch_tasks(deviceId: str = Query(...), limit: int = Query(1, ge=1, le=5), x_api_key: str = Header(None)):
    await verify_agent_key(x_api_key)
    await ensure_connected()
    
    tasks = await agent_service.fetch_tasks(deviceId, limit)
    
    if isinstance(tasks, str):  # Handling error strings returned by service
        if tasks == "unregistered": raise HTTPException(status_code=404, detail="Device not registered")
        return {"tasks": [], "count": 0, "message": f"Device is {tasks}", "deviceStatus": tasks, "shouldStop": tasks in ["restricted", "blocked"]}
    
    return {"tasks": tasks, "count": len(tasks), "deviceStatus": "online", "shouldStop": False}

@router.get("/logs")
async def get_activity_logs(limit: int = 100, level: str = None, device_id: str = Query(None, alias="deviceId"), event_type: str = Query(None, alias="eventType"), x_api_key: str = Header(None)):
    await verify_agent_key(x_api_key)
    await ensure_connected()
    logs = await agent_service.get_logs(limit, level, device_id, event_type)
    return {"logs": logs, "count": len(logs)}