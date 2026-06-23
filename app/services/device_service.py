# app/services/device_service.py
from datetime import datetime, timezone
from bson import ObjectId
from .base_service import BaseService

class DeviceService(BaseService):
    def __init__(self):
        super().__init__()  # Initializes self.db from BaseService

    async def get_all_devices(self):
        # We use 'await' because we are using motor (async MongoDB driver)
        cursor = self.db.devices.find().sort("lastHeartbeat", -1)
        return await cursor.to_list(500)

    async def get_device_stats(self):
        pipeline = [
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ]
        results = await self.db.devices.aggregate(pipeline).to_list(None)
        stats = {r["_id"]: r["count"] for r in results}
        return {
            "total": await self.db.devices.count_documents({}),
            "online": stats.get("online", 0),
            "offline": stats.get("offline", 0),
            "error": stats.get("error", 0),
            "paused": stats.get("paused", 0),
            "restricted": stats.get("restricted", 0),
        }

    async def get_device_by_id(self, device_id: str):
        return await self.device_service.get_device_by_id(device_id)

    async def update_device(self, device_id: str, update_data: dict):
        update_data["updatedAt"] = datetime.now(timezone.utc).isoformat()
        return await self.db.devices.update_one(
            {"deviceId": device_id}, {"$set": update_data}
        )

    async def delete_device(self, device_id: str):
        # Clean up associated tasks first
        await self.db.tasks.delete_many({"deviceId": device_id, "status": {"$in": ["pending", "assigned"]}})
        return await self.db.devices.delete_one({"deviceId": device_id})

    async def queue_command(self, device_id: str, cmd: str):
        return await self.db.devices.update_one(
            {"deviceId": device_id},
            {"$set": {"pendingCommand": cmd, "commandAt": datetime.now(timezone.utc).isoformat()}}
        )

    async def get_target_devices(self):
        return await self.db.devices.find({"status": {"$nin": ["restricted", "blocked"]}}).to_list(500)