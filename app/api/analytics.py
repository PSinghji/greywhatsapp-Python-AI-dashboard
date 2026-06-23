"""
Analytics API - Campaign and device performance metrics.
"""
from fastapi import APIRouter, Query
from bson import ObjectId
from app.database import get_db
from app.services.device_service import DeviceService
router = APIRouter()


@router.get("/overview")
async def analytics_overview(campaignId: str = Query(None)):
    """Get overall analytics."""
    db = get_db()
    match_stage = {}
    if campaignId:
        match_stage["campaignId"] = campaignId

    total = await db.tasks.count_documents(match_stage)
    sent = await db.tasks.count_documents({**match_stage, "status": "completed"})
    failed = await db.tasks.count_documents({**match_stage, "status": "failed"})
    pending = await db.tasks.count_documents({**match_stage, "status": {"$in": ["pending", "assigned", "in_progress"]}})

    success_rate = round((sent / total * 100), 1) if total > 0 else 0

    return {
        "total": total,
        "sent": sent,
        "failed": failed,
        "pending": pending,
        "successRate": success_rate,
    }


@router.get("/campaigns")
async def campaign_analytics():
    """Get per-campaign performance."""
    db = get_db()
    pipeline = [
        {"$group": {
            "_id": "$campaignId",
            "campaignName": {"$first": "$campaignName"},
            "total": {"$sum": 1},
            "completed": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}},
            "failed": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}},
            "pending": {"$sum": {"$cond": [{"$in": ["$status", ["pending", "assigned", "in_progress"]]}, 1, 0]}},
        }},
        {"$sort": {"total": -1}},
    ]
    results = await db.tasks.aggregate(pipeline).to_list(100)
    for r in results:
        r["campaignId"] = r.pop("_id")
        r["successRate"] = round((r["completed"] / r["total"] * 100), 1) if r["total"] > 0 else 0
    return results


@router.get("/devices")
async def device_analytics():
    """Get per-device performance metrics."""
    db = get_db()
    pipeline = [
        {"$group": {
            "_id": "$deviceId",
            "total": {"$sum": 1},
            "completed": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}},
            "failed": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}},
            "pending": {"$sum": {"$cond": [{"$in": ["$status", ["pending", "assigned", "in_progress"]]}, 1, 0]}},
        }},
        {"$sort": {"completed": -1}},
    ]
    results = await db.tasks.aggregate(pipeline).to_list(100)

    # Enrich with device info
    for r in results:
        r["deviceId"] = r.pop("_id")
        r["successRate"] = round((r["completed"] / r["total"] * 100), 1) if r["total"] > 0 else 0
        device = await db.devices.find_one({"deviceId": r["deviceId"]})
        r["deviceName"] = device.get("deviceName", r["deviceId"]) if device else r["deviceId"]
        r["status"] = device.get("status", "unknown") if device else "unknown"

    return results


@router.get("/timeline")
async def delivery_timeline(campaignId: str = Query(None), days: int = Query(7, ge=1, le=90)):
    """Get message delivery timeline (hourly buckets)."""
    db = get_db()
    from datetime import datetime, timezone, timedelta

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    match_stage = {"deliveredAt": {"$gte": cutoff}, "status": "completed"}
    if campaignId:
        match_stage["campaignId"] = campaignId

    tasks = await db.tasks.find(match_stage).sort("deliveredAt", 1).to_list(10000)

    # Group by hour
    timeline = {}
    for t in tasks:
        if t.get("deliveredAt"):
            hour = t["deliveredAt"][:13]  # YYYY-MM-DDTHH
            timeline[hour] = timeline.get(hour, 0) + 1

    return [{"hour": k, "count": v} for k, v in sorted(timeline.items())]
