"""
Tasks API - View and manage individual message tasks.
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from bson import ObjectId
from datetime import datetime, timezone
import io
import csv

from app.database import get_db
from app.models.schemas import TaskStatus

router = APIRouter()


def serialize(doc):
    if doc is None:
        return None
    doc["_id"] = str(doc["_id"])
    return doc


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
    db = get_db()
    query = {}
    if status:
        query["status"] = status
    if device_id:
        query["deviceId"] = device_id
    if campaign_id:
        query["campaignId"] = campaign_id
    if search:
        query["recipient"] = {"$regex": search, "$options": "i"}

    tasks = await db.tasks.find(query).sort("updatedAt", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.tasks.count_documents(query)

    # Build device lookup map for device names and phone numbers
    device_ids = list(set(t.get("deviceId") for t in tasks if t.get("deviceId")))
    device_map = {}
    if device_ids:
        devices = await db.devices.find({"deviceId": {"$in": device_ids}}).to_list(500)
        for d in devices:
            device_map[d["deviceId"]] = {
                "name": d.get("deviceName", d.get("deviceId", "")),
                "phone": d.get("phoneNumber", ""),
            }

    # Build campaign lookup map for campaign names
    campaign_ids = list(set(t.get("campaignId") for t in tasks if t.get("campaignId")))
    campaign_map = {}
    if campaign_ids:
        try:
            campaigns = await db.campaigns.find(
                {"_id": {"$in": [ObjectId(cid) for cid in campaign_ids if cid]}}
            ).to_list(500)
            for c in campaigns:
                campaign_map[str(c["_id"])] = c.get("name", "")
        except Exception:
            pass

    # Enrich tasks with device and campaign info
    result = []
    for t in tasks:
        t["_id"] = str(t["_id"])
        did = t.get("deviceId", "")
        t["deviceName"] = device_map.get(did, {}).get("name", did)
        t["devicePhone"] = device_map.get(did, {}).get("phone", "")
        cid = t.get("campaignId", "")
        t["campaignName"] = t.get("campaignName") or campaign_map.get(cid, "")
        # Alias errorMessage as failureReason for frontend compatibility
        t["failureReason"] = t.get("errorMessage", "")
        result.append(t)

    return {"tasks": result, "total": total, "skip": skip, "limit": limit}


@router.get("/stats")
async def task_stats():
    """Get task statistics."""
    db = get_db()
    total = await db.tasks.count_documents({})
    pending = await db.tasks.count_documents({"status": "pending"})
    assigned = await db.tasks.count_documents({"status": "assigned"})
    in_progress = await db.tasks.count_documents({"status": "in_progress"})
    completed = await db.tasks.count_documents({"status": "completed"})
    failed = await db.tasks.count_documents({"status": "failed"})
    invalid = await db.tasks.count_documents({"status": "invalid_number"})
    restricted = await db.tasks.count_documents({"status": "account_restricted"})
    return {
        "total": total,
        "pending": pending,
        "assigned": assigned,
        "inProgress": in_progress,
        "completed": completed,
        "failed": failed,
        "invalidNumber": invalid,
        "accountRestricted": restricted,
    }


@router.get("/export")
async def export_tasks(
    status: str = None,
    campaign_id: str = None,
    device_id: str = None,
):
    """Export tasks as CSV with device name, phone, and campaign name."""
    db = get_db()
    query = {}
    if status:
        query["status"] = status
    if campaign_id:
        query["campaignId"] = campaign_id
    if device_id:
        query["deviceId"] = device_id

    tasks = await db.tasks.find(query).sort("updatedAt", -1).to_list(50000)

    # Build device lookup
    device_ids = list(set(t.get("deviceId") for t in tasks if t.get("deviceId")))
    device_map = {}
    if device_ids:
        devices = await db.devices.find({"deviceId": {"$in": device_ids}}).to_list(500)
        for d in devices:
            device_map[d["deviceId"]] = {
                "name": d.get("deviceName", ""),
                "phone": d.get("phoneNumber", ""),
            }

    # Build campaign lookup
    campaign_ids = list(set(t.get("campaignId") for t in tasks if t.get("campaignId")))
    campaign_map = {}
    if campaign_ids:
        try:
            campaigns = await db.campaigns.find(
                {"_id": {"$in": [ObjectId(cid) for cid in campaign_ids if cid]}}
            ).to_list(500)
            for c in campaigns:
                campaign_map[str(c["_id"])] = c.get("name", "")
        except Exception:
            pass

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Recipient", "Status", "Campaign Name", "Device ID", "Device Name", "Device Phone", "Error/Reason", "Delivered At", "Last Updated"])
    for t in tasks:
        did = t.get("deviceId", "")
        cid = t.get("campaignId", "")
        writer.writerow([
            t.get("recipient", ""),
            t.get("status", ""),
            t.get("campaignName") or campaign_map.get(cid, ""),
            did,
            device_map.get(did, {}).get("name", did),
            device_map.get(did, {}).get("phone", ""),
            t.get("errorMessage", ""),
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
    db = get_db()
    try:
        task = await db.tasks.find_one({"_id": ObjectId(task_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid task ID")
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["status"] not in ["failed"]:
        raise HTTPException(status_code=400, detail=f"Cannot retry task with status '{task['status']}'. Only 'failed' tasks can be retried.")
    await db.tasks.update_one(
        {"_id": ObjectId(task_id)},
        {"$set": {"status": "pending", "errorMessage": None, "retryCount": 0,
                  "updatedAt": datetime.now(timezone.utc).isoformat()}}
    )
    return {"success": True}


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    """Delete a single task."""
    db = get_db()
    try:
        result = await db.tasks.delete_one({"_id": ObjectId(task_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid task ID")
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True}
