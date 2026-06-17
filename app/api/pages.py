"""
Pages Router - Serve HTML templates for the dashboard frontend.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("pages/dashboard.html", {"request": request})


@router.get("/devices", response_class=HTMLResponse)
async def devices_page(request: Request):
    return templates.TemplateResponse("pages/devices.html", {"request": request})


@router.get("/campaigns", response_class=HTMLResponse)
async def campaigns_page(request: Request):
    return templates.TemplateResponse("pages/campaigns.html", {"request": request})


@router.get("/tasks", response_class=HTMLResponse)
async def tasks_page(request: Request):
    return templates.TemplateResponse("pages/tasks.html", {"request": request})


@router.get("/tuning", response_class=HTMLResponse)
async def tuning_page(request: Request):
    return templates.TemplateResponse("pages/tuning.html", {"request": request})


@router.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request):
    return templates.TemplateResponse("pages/analytics.html", {"request": request})


@router.get("/media", response_class=HTMLResponse)
async def media_page(request: Request):
    return templates.TemplateResponse("pages/media.html", {"request": request})


@router.get("/api-keys", response_class=HTMLResponse)
async def api_keys_page(request: Request):
    return templates.TemplateResponse("pages/apikeys.html", {"request": request})


@router.get("/activity-logs", response_class=HTMLResponse)
async def activity_logs_page(request: Request):
    return templates.TemplateResponse("pages/activity_logs.html", {"request": request})


@router.get("/distribution", response_class=HTMLResponse)
async def distribution_page(request: Request):
    return templates.TemplateResponse("pages/distribution.html", {"request": request})


@router.get("/reports/non-whatsapp", response_class=HTMLResponse)
async def non_whatsapp_report_page(request: Request):
    return templates.TemplateResponse("pages/non_whatsapp_report.html", {"request": request})


@router.get("/reports/campaign-wise", response_class=HTMLResponse)
async def campaign_wise_report_page(request: Request):
    return templates.TemplateResponse("pages/campaign_wise_report.html", {"request": request})


@router.get("/reports/campaigns", response_class=HTMLResponse)
async def reports_campaigns_page(request: Request):
    return templates.TemplateResponse("pages/campaign_wise_report.html", {"request": request})


@router.get("/reports/campaigns/{campaign_id}", response_class=HTMLResponse)
async def campaign_report_page(request: Request, campaign_id: str):
    return templates.TemplateResponse("pages/campaign_report.html", {"request": request, "campaign_id": campaign_id})


# ═══════════════════════════════════════════════════════════
#  NEW PAGES: Daily Reports & Device Communication
# ═══════════════════════════════════════════════════════════

@router.get("/reports/daily", response_class=HTMLResponse)
async def daily_reports_page(request: Request):
    return templates.TemplateResponse("pages/daily_reports.html", {"request": request})


@router.get("/device-communication", response_class=HTMLResponse)
async def device_communication_page(request: Request):
    return templates.TemplateResponse("pages/device_comm.html", {"request": request})
