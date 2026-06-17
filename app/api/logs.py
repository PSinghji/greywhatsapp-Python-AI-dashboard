"""
Activity Logs API - Dashboard-accessible endpoint for viewing activity logs.
No API key required (for internal dashboard use).
"""
from fastapi import APIRouter, Query
from app.database import get_db

router = APIRouter()


@router.get("")
async def get_logs(
    limit: int = Query(200, ge=1, le=1000),
    level: str = Query(None),
    deviceId: str = Query(None),
    eventType: str = Query(None),
    campaignId: str = Query(None),
):
    """Get recent activity logs for the dashboard."""
    db = get_db()

    query = {}
    if level:
        query["level"] = level
    if deviceId:
        query["deviceId"] = deviceId
    if eventType:
        query["eventType"] = eventType
    if campaignId:
        query["campaignId"] = campaignId

    logs = await db.activity_logs.find(query).sort("createdAt", -1).limit(limit).to_list(limit)
    for log in logs:
        log["_id"] = str(log["_id"])
    return {"logs": logs, "count": len(logs)}


@router.delete("/clear")
async def clear_logs(older_than_days: int = Query(30, ge=1)):
    """Clear logs older than N days."""
    from datetime import datetime, timezone, timedelta
    db = get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
    result = await db.activity_logs.delete_many({"createdAt": {"$lt": cutoff}})
    return {"success": True, "deletedCount": result.deleted_count}
