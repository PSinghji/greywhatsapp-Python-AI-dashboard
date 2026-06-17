"""
WhatsApp Campaign Dashboard - Main Application
FastAPI + MongoDB + Jinja2 HTML Templates
"""
import os
import asyncio
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager

from app.database import connect_db, close_db, seed_defaults
from app.api.devices import router as devices_router
from app.api.campaigns import router as campaigns_router
from app.api.tasks import router as tasks_router
from app.api.tuning import router as tuning_router
from app.api.media import router as media_router
from app.api.apikeys import router as apikeys_router
from app.api.analytics import router as analytics_router
from app.api.agent import router as agent_router, mark_stale_devices_offline, mark_stale_tasks_as_failed
from app.api.logs import router as logs_router
from app.api.pages import router as pages_router
from app.api.daily_reports import router as daily_reports_router
from app.api.device_comm import router as device_comm_router, start_device_comm_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    await connect_db()
    await seed_defaults()

    # Start background tasks
    offline_task = asyncio.create_task(mark_stale_devices_offline())
    stale_task = asyncio.create_task(mark_stale_tasks_as_failed())

    # Start device communication auto-scheduler
    await start_device_comm_scheduler()

    # Seed conversation templates on first run
    from app.services.seed_templates import seed_conversation_templates
    asyncio.create_task(seed_conversation_templates())

    print("[Startup] Background checkers started")
    print("[Startup] Device communication auto-scheduler started")
    yield
    offline_task.cancel()
    stale_task.cancel()
    await close_db()


app = FastAPI(
    title="WhatsApp Campaign Dashboard",
    description="Central control panel for managing WhatsApp campaign agents",
    version="2.1.0",
    lifespan=lifespan,
)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

import os as _os
_os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Include API routers
app.include_router(pages_router, tags=["Pages"])
app.include_router(devices_router, prefix="/api/devices", tags=["Devices"])
app.include_router(campaigns_router, prefix="/api/campaigns", tags=["Campaigns"])
app.include_router(tasks_router, prefix="/api/tasks", tags=["Tasks"])
app.include_router(tuning_router, prefix="/api/tuning", tags=["Tuning Profiles"])
app.include_router(media_router, prefix="/api/media", tags=["Media"])
app.include_router(apikeys_router, prefix="/api/apikeys", tags=["API Keys"])
app.include_router(analytics_router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(agent_router, prefix="/api/agent", tags=["Agent API"])
app.include_router(logs_router, prefix="/api/logs", tags=["Activity Logs"])
app.include_router(daily_reports_router, prefix="/api/daily-reports", tags=["Daily Reports"])
app.include_router(device_comm_router, prefix="/api/device-comm", tags=["Device Communication"])


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host=host, port=port, reload=True)
