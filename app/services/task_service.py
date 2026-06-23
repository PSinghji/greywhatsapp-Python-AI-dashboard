# app/services/task_service.py
from datetime import datetime, timezone
from bson import ObjectId
from .base_service import BaseService

class TaskService(BaseService):
    def __init__(self):
        super().__init__()

    async def list_tasks_enriched(self, status=None, device_id=None, campaign_id=None, search=None, skip=0, limit=100):
        """Fetches tasks and enriches them with Device and Campaign names."""
        query = {}
        if status: query["status"] = status
        if device_id: query["deviceId"] = device_id
        if campaign_id: query["campaignId"] = campaign_id
        if search: query["recipient"] = {"$regex": search, "$options": "i"}

        tasks = await self.db.tasks.find(query).sort("updatedAt", -1).skip(skip).limit(limit).to_list(limit)
        total = await self.db.tasks.count_documents(query)

        # Build device lookup map
        device_ids = list({t.get("deviceId") for t in tasks if t.get("deviceId")})
        device_map = {}
        if device_ids:
            devices = await self.db.devices.find({"deviceId": {"$in": device_ids}}).to_list(None)
            for d in devices:
                device_map[d["deviceId"]] = {
                    "name": d.get("deviceName", d.get("deviceId", "")),
                    "phone": d.get("phoneNumber", ""),
                }

        # Build campaign lookup map
        campaign_ids = list({t.get("campaignId") for t in tasks if t.get("campaignId")})
        campaign_map = {}
        if campaign_ids:
            try:
                c_obj_ids = [ObjectId(cid) for cid in campaign_ids if cid and len(cid) == 24]
                campaigns = await self.db.campaigns.find({"_id": {"$in": c_obj_ids}}).to_list(None)
                for c in campaigns:
                    campaign_map[str(c["_id"])] = c.get("name", "")
            except Exception:
                pass

        # Enrich tasks
        result = []
        for t in tasks:
            t["_id"] = str(t["_id"])
            did = t.get("deviceId", "")
            cid = t.get("campaignId", "")
            t["deviceName"] = device_map.get(did, {}).get("name", did)
            t["devicePhone"] = device_map.get(did, {}).get("phone", "")
            t["campaignName"] = t.get("campaignName") or campaign_map.get(cid, "")
            t["failureReason"] = t.get("errorMessage", "")
            result.append(t)

        return {"tasks": result, "total": total}

    async def get_task_stats(self):
        """Highly optimized single-query task statistics."""
        pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
        results = await self.db.tasks.aggregate(pipeline).to_list(None)
        
        # Map results to a dictionary
        stats = {r["_id"]: r["count"] for r in results}
        total = sum(stats.values())
        
        return {
            "total": total,
            "pending": stats.get("pending", 0),
            "assigned": stats.get("assigned", 0),
            "inProgress": stats.get("in_progress", 0),
            "completed": stats.get("completed", 0),
            "failed": stats.get("failed", 0),
            "invalidNumber": stats.get("invalid_number", 0),
            "accountRestricted": stats.get("account_restricted", 0),
        }

    async def retry_task(self, task_id: str):
        """Attempts to reset a failed task to pending."""
        try:
            obj_id = ObjectId(task_id)
        except Exception:
            return "invalid_id"

        task = await self.db.tasks.find_one({"_id": obj_id})
        if not task:
            return "not_found"
        if task.get("status") != "failed":
            return "invalid_status"

        await self.db.tasks.update_one(
            {"_id": obj_id},
            {"$set": {
                "status": "pending", 
                "errorMessage": None, 
                "retryCount": 0,
                "updatedAt": datetime.now(timezone.utc).isoformat()
            }}
        )
        return "success"

    async def delete_task(self, task_id: str):
        """Safely deletes a task."""
        try:
            result = await self.db.tasks.delete_one({"_id": ObjectId(task_id)})
            return result.deleted_count > 0
        except Exception:
            return False