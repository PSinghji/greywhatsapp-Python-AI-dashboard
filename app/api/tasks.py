"""
Tasks API - View and manage individual message tasks.
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from datetime import datetime
import io
import csv

from app.services.task_service import TaskService

router = APIRouter()
task_service = TaskService()

@router.get("")
async def list_tasks(
    status: str = None,
    device_id: str = None,
    campaign_id: str = None,
    search: str = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=50000),
):
    """List tasks with optional filters, including device name/phone and campaign name."""
    data = await task_service.list_tasks_enriched(status, device_id, campaign_id, search, skip, limit)
    return {"tasks": data["tasks"], "total": data["total"], "skip": skip, "limit": limit}

@router.get("/stats")
async def task_stats():
    """Get task statistics via optimized service."""
    return await task_service.get_task_stats()

@router.get("/export")
async def export_tasks(
    status: str = None,
    campaign_id: str = None,
    device_id: str = None,
):
    """Export tasks as CSV."""
    # We reuse the enriched list logic but without pagination limits (up to 50k)
    data = await task_service.list_tasks_enriched(status, device_id, campaign_id, None, 0, 50000)
    tasks = data["tasks"]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Recipient", "Status", "Campaign Name", "Device ID", "Device Name", "Device Phone", "Error/Reason", "Delivered At", "Last Updated"])
    
    for t in tasks:
        writer.writerow([
            t.get("recipient", ""),
            t.get("status", ""),
            t.get("campaignName", ""),
            t.get("deviceId", ""),
            t.get("deviceName", ""),
            t.get("devicePhone", ""),
            t.get("failureReason", ""),
            t.get("deliveredAt", ""),
            t.get("updatedAt", ""),
        ])

    output.seek(0)
    filename = f"tasks_export_{status or 'all'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

@router.post("/{task_id}/retry")
async def retry_task(task_id: str):
    """Retry a single failed task (not invalid_number or account_restricted)."""
    result = await task_service.retry_task(task_id)
    
    if result == "invalid_id":
        raise HTTPException(status_code=400, detail="Invalid task ID")
    elif result == "not_found":
        raise HTTPException(status_code=404, detail="Task not found")
    elif result == "invalid_status":
        raise HTTPException(status_code=400, detail="Cannot retry task. Only 'failed' tasks can be retried.")
        
    return {"success": True}

@router.delete("/{task_id}")
async def delete_task(task_id: str):
    """Delete a single task."""
    deleted = await task_service.delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found or invalid ID")
    return {"success": True}