"""
Daily Reports API - Consolidated daily performance tracking.
MODIFIED: Updated to handle 'createdAt' as a String (Regex based filtering).
"""
from fastapi import APIRouter, Query
from datetime import datetime, timezone, timedelta
from app.database import get_db
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/summary")
async def daily_summary(days: int = Query(30, ge=1, le=365)):
    db = get_db()
    # For String dates, we generate a list of date prefixes for the last N days
    dates_to_check = []
    for i in range(days):
        d = (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d")
        dates_to_check.append(d)

    pipeline = [
        # Match documents where createdAt string starts with any of our target dates
        {"$match": {"createdAt": {"$regex": f"^({'|'.join(dates_to_check)})"}}},
        {"$addFields": {
            "day": {"$substr": ["$createdAt", 0, 10]}
        }},
        {"$group": {
            "_id": "$day",
            "totalTasks": {"$sum": 1},
            "completed": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}},
            "failed": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}},
            "invalidNumber": {"$sum": {"$cond": [{"$eq": ["$status", "invalid_number"]}, 1, 0]}},
            "campaigns": {"$addToSet": "$campaignId"},
            "devices": {"$addToSet": "$deviceId"},
        }},
        {"$addFields": {
            "campaignCount": {"$size": "$campaigns"},
            "deviceCount": {"$size": "$devices"},
            "deliveryRate": {
                "$cond": [
                    {"$gt": ["$totalTasks", 0]},
                    {"$round": [{"$multiply": [{"$divide": ["$completed", "$totalTasks"]}, 100]}, 1]},
                    0
                ]
            },
        }},
        {"$project": {"campaigns": 0, "devices": 0}},
        {"$sort": {"_id": 1}},
    ]

    results = await db.tasks.aggregate(pipeline).to_list(days)
    for r in results:
        r["date"] = r.pop("_id")

    return {"days": results, "totalDays": len(results)}

@router.get("/overview-totals")
async def overview_totals():
    db = get_db()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # All-time remains the same
    all_total = await db.tasks.count_documents({})
    all_completed = await db.tasks.count_documents({"status": "completed"})
    all_failed = await db.tasks.count_documents({"status": "failed"})
    
    # Today stats using Regex for String matching
    today_filter = {"createdAt": {"$regex": f"^{today_str}"}}
    today_total = await db.tasks.count_documents(today_filter)
    today_completed = await db.tasks.count_documents({**today_filter, "status": "completed"})
    today_failed = await db.tasks.count_documents({**today_filter, "status": "failed"})

    return {
        "allTime": {
            "total": all_total,
            "completed": all_completed,
            "failed": all_failed,
            "deliveryRate": round((all_completed / all_total * 100), 1) if all_total > 0 else 0,
        },
        "today": {
            "total": today_total,
            "completed": today_completed,
            "failed": today_failed,
            "deliveryRate": round((today_completed / today_total * 100), 1) if today_total > 0 else 0,
        },
        "campaigns": {"total": await db.campaigns.count_documents({}), "active": await db.campaigns.count_documents({"status": "running"})},
        "devices": {"total": await db.devices.count_documents({}), "online": await db.devices.count_documents({"status": "online"})}
    }

@router.get("/hourly-trend")
async def hourly_trend(date: str = Query(None)):
    db = get_db()
    if not date:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    pipeline = [
        # Regex match for the start of the string (YYYY-MM-DD)
        {"$match": {"createdAt": {"$regex": f"^{date}"}}},
        {"$addFields": {
            # Extract characters at position 11 and 12 (the hour)
            "hour": {"$substr": ["$createdAt", 11, 2]}
        }},
        {"$group": {
            "_id": "$hour",
            "total": {"$sum": 1},
            "completed": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}},
            "failed": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}},
        }},
        {"$sort": {"_id": 1}},
    ]

    results = await db.tasks.aggregate(pipeline).to_list(24)
    existing_hours = {r["_id"]: r for r in results}
    formatted_results = []
    
    for h in range(24):
        hour_str = f"{h:02d}"
        if hour_str in existing_hours:
            r = existing_hours[hour_str]
            formatted_results.append({
                "hour": hour_str,
                "total": r["total"],
                "completed": r["completed"],
                "failed": r["failed"]
            })
        else:
            formatted_results.append({"hour": hour_str, "total": 0, "completed": 0, "failed": 0})

    return {"date": date, "hours": formatted_results}

@router.get("/device-performance")
async def device_daily_performance(days: int = Query(30, ge=1, le=365)):
    db = get_db()
    dates_to_check = [(datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
    
    pipeline = [
        {"$match": {"createdAt": {"$regex": f"^({'|'.join(dates_to_check)})"}, "deviceId": {"$ne": None}}},
        {"$addFields": {"day": {"$substr": ["$createdAt", 0, 10]}}},
        {"$group": {
            "_id": {"day": "$day", "deviceId": "$deviceId"},
            "total": {"$sum": 1},
            "completed": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}},
        }},
        {"$sort": {"_id.day": -1}}
    ]
    results = await db.tasks.aggregate(pipeline).to_list(1000)
    for r in results:
        r["date"] = r["_id"]["day"]
        r["deviceId"] = r["_id"]["deviceId"]
        del r["_id"]
    return {"records": results}

@router.get("/campaign-daily")
async def campaign_daily_stats(days: int = Query(30, ge=1, le=365)):
    db = get_db()
    dates_to_check = [(datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]

    pipeline = [
        {"$match": {"createdAt": {"$regex": f"^({'|'.join(dates_to_check)})"}}},
        {"$addFields": {"day": {"$substr": ["$createdAt", 0, 10]}}},
        {"$group": {
            "_id": {"day": "$day", "campaignId": "$campaignId"},
            "campaignName": {"$first": "$campaignName"},
            "total": {"$sum": 1},
            "completed": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}},
        }},
        {"$sort": {"_id.day": -1}}
    ]
    results = await db.tasks.aggregate(pipeline).to_list(1000)
    for r in results:
        r["date"] = r["_id"]["day"]
        r["campaignId"] = r["_id"]["campaignId"]
        del r["_id"]
    return {"records": results}

@router.get("/device-health")
async def device_health_report():
    db = get_db()
    devices = await db.devices.find({}).to_list(100)
    result = []
    for d in devices:
        device_id = d.get("deviceId", "")
        total = await db.tasks.count_documents({"deviceId": device_id})
        completed = await db.tasks.count_documents({"deviceId": device_id, "status": "completed"})
        result.append({
            "deviceId": device_id,
            "deviceName": d.get("deviceName", device_id),
            "status": d.get("status", "unknown"),
            "totalTasks": total,
            "completed": completed,
            "successRate": round((completed / total * 100), 1) if total > 0 else 0,
        })
    return {"devices": result}