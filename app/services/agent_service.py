# app/services/agent_service.py
from datetime import datetime, timezone, timedelta
from bson import ObjectId
import random
import logging
from .base_service import BaseService
from .ai_service import AIService

logger = logging.getLogger(__name__)

class AgentService(BaseService):
    def __init__(self):
        super().__init__()
        self.ai_service = AIService()

    async def log_activity(self, event_type: str, message: str, device_id: str = None,
                           campaign_id: str = None, task_id: str = None,
                           level: str = "info", metadata: dict = None):
        try:
            doc = {
                "eventType": event_type,
                "deviceId": device_id,
                "campaignId": campaign_id,
                "taskId": task_id,
                "message": message,
                "level": level,
                "metadata": metadata,
                "createdAt": datetime.now(timezone.utc).isoformat(),
            }
            await self.db.activity_logs.insert_one(doc)
        except Exception as e:
            logger.error(f"[Activity Log] Failed: {e}")

    # ─── BACKGROUND TASK LOGIC ─────────────────────────────
    
    async def check_offline_devices(self):
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=45)).isoformat()
        stale_devices = await self.db.devices.find({
            "status": {"$in": ["online", "busy", "idle"]},
            "lastHeartbeat": {"$lt": cutoff}
        }).to_list(100)
        
        if stale_devices:
            device_ids = [d["deviceId"] for d in stale_devices]
            result = await self.db.devices.update_many(
                {"status": {"$in": ["online", "busy", "idle"]}, "lastHeartbeat": {"$lt": cutoff}},
                {"$set": {"status": "offline", "updatedAt": datetime.now(timezone.utc).isoformat()}}
            )
            if result.modified_count > 0:
                await self.log_activity("device_offline_auto", f"{result.modified_count} devices offline", level="warning", metadata={"deviceIds": device_ids})

    async def check_stale_tasks(self):
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        stale_tasks = await self.db.tasks.find({"status": "assigned", "assignedAt": {"$lt": cutoff}}).to_list(200)
        
        if stale_tasks:
            now = datetime.now(timezone.utc).isoformat()
            online_devices = await self.db.devices.find({
                "status": {"$in": ["online", "idle"]},
                "accountStatus": {"$nin": ["restricted", "blocked"]}
            }).to_list(500)
            online_device_ids = [d["deviceId"] for d in online_devices]
            
            for task in stale_tasks:
                old_device = task.get("deviceId", "")
                available_devices = [d for d in online_devices if d["deviceId"] != old_device]

                if available_devices:
                    # Ask the AI to pick the best device based on battery, memory, and success rate!
                    new_device = await self.ai_service.get_best_device_for_task(available_devices)
                elif online_devices:
                    new_device = online_devices[0]["deviceId"]
                else:
                    new_device = None


                update = {"status": "pending", "assignedAt": None, "updatedAt": now}
                if new_device: update["deviceId"] = new_device
                
                await self.db.tasks.update_one({"_id": task["_id"]}, {"$set": update, "$inc": {"retryCount": 1}})
            await self.log_activity("stale_tasks_reshuffled", f"{len(stale_tasks)} stuck tasks reshuffled", level="warning")

    async def run_campaign_watchdog(self):
        now = datetime.now(timezone.utc).isoformat()
        running_campaigns = await self.db.campaigns.find({"status": "running"}).to_list(100)
        online_devices = await self.db.devices.find({
            "status": {"$in": ["online", "idle"]}, "accountStatus": {"$nin": ["restricted", "blocked"]}
        }).to_list(500)
        online_device_ids = [d["deviceId"] for d in online_devices]
        
        for campaign in running_campaigns:
            cid = str(campaign["_id"])
            if online_device_ids:
                # 1. Reassign orphaned tasks
                orphaned_tasks = await self.db.tasks.find({
                    "campaignId": cid, "status": {"$in": ["pending", "assigned"]}, "deviceId": {"$nin": online_device_ids + [None, ""]}
                }).to_list(1000)
                for task in orphaned_tasks:
                    await self.db.tasks.update_one(
                        {"_id": task["_id"]},
                        {"$set": {"deviceId": random.choice(online_device_ids), "status": "pending", "assignedAt": None, "updatedAt": now}}
                    )

                # 2. Retry stuck failed tasks
                stuck_failed = await self.db.tasks.find({
                    "campaignId": cid, "status": "failed", "retryCount": {"$lt": 5},
                    "errorMessage": {"$not": {"$regex": "not on WhatsApp|invalid_number|Number not on"}}
                }).to_list(500)
                for task in stuck_failed:
                    old_device = task.get("deviceId", "")
                    available = [d for d in online_device_ids if d != old_device]
                    new_device = random.choice(available) if available else random.choice(online_device_ids)
                    await self.db.tasks.update_one(
                        {"_id": task["_id"]},
                        {"$set": {"status": "pending", "deviceId": new_device, "assignedAt": None, "errorMessage": None, "updatedAt": now}, "$inc": {"retryCount": 1}}
                    )
            
            # 3. Check Campaign Completion
            remaining = await self.db.tasks.count_documents({"campaignId": cid, "status": {"$in": ["pending", "assigned", "in_progress"]}})
            if remaining == 0:
                retryable = await self.db.tasks.count_documents({
                    "campaignId": cid, "status": "failed", "retryCount": {"$lt": 5},
                    "errorMessage": {"$not": {"$regex": "not on WhatsApp|invalid_number|Number not on"}}
                })
                if retryable == 0:
                    await self.db.campaigns.update_one({"_id": ObjectId(cid)}, {"$set": {"status": "completed", "completedAt": now, "updatedAt": now}})

    # ─── CORE AGENT LOGIC ──────────────────────────────────
    
    async def register_device(self, data: dict):
        now = datetime.now(timezone.utc).isoformat()
        existing = await self.db.devices.find_one({"deviceId": data["deviceId"]})
        
        if existing:
            new_status = existing.get("status", "")
            if new_status not in ("restricted", "blocked"):
                new_status = "online"
            
            await self.db.devices.update_one(
                {"deviceId": data["deviceId"]},
                {"$set": {
                    "deviceName": data.get("deviceName") or existing.get("deviceName"),
                    "phoneNumber": data.get("phoneNumber") or existing.get("phoneNumber"),
                    "androidVersion": data.get("androidVersion"),
                    "model": data.get("model"),
                    "appVersion": data.get("appVersion"),
                    "status": new_status,
                    "lastHeartbeat": now,
                    "updatedAt": now,
                }}
            )
            return {"success": True, "deviceId": data["deviceId"], "deviceStatus": new_status, "shouldStop": new_status in ("restricted", "blocked")}
        else:
            device = {
                "deviceId": data["deviceId"],
                "deviceName": data.get("deviceName") or f"Device-{data['deviceId'][:8]}",
                "status": "online",
                "accountStatus": "active",
                "lastHeartbeat": now,
                "createdAt": now,
                "updatedAt": now,
            }
            await self.db.devices.insert_one(device)
            return {"success": True, "deviceId": data["deviceId"], "deviceStatus": "online", "shouldStop": False}

    async def process_heartbeat(self, data: dict):
        now = datetime.now(timezone.utc).isoformat()
        device = await self.db.devices.find_one({"deviceId": data["deviceId"]})
        if not device: return None

        if data.get("accountStatus") in ["restricted", "blocked"]:
            new_status = data["accountStatus"]
        elif device.get("status") in ("restricted", "blocked"):
            new_status = device.get("status")
        else:
            new_status = "online"

        update_data = {
            "batteryLevel": data.get("batteryLevel"),
            "status": new_status,
            "lastHeartbeat": now,
            "updatedAt": now,
        }
        await self.db.devices.update_one({"deviceId": data["deviceId"]}, {"$set": update_data})
        
        pending_command = device.get("pendingCommand")
        if pending_command:
            await self.db.devices.update_one({"deviceId": data["deviceId"]}, {"$set": {"pendingCommand": None}})
            
        return {"success": True, "command": pending_command, "deviceStatus": new_status, "shouldStop": new_status in ("restricted", "blocked")}

    async def fetch_tasks(self, device_id: str, limit: int):
        device = await self.db.devices.find_one({"deviceId": device_id})
        if not device: return "unregistered"
        
        status = device.get("status", "")
        if status in ["restricted", "blocked", "paused"]: return status

        running_campaigns = await self.db.campaigns.find({"status": "running"}).to_list(500)
        running_campaign_ids = [str(c["_id"]) for c in running_campaigns]
        if not running_campaign_ids: return []

        last_idx = device.get("lastCampaignIndex", 0) % max(len(running_campaign_ids), 1)
        mixed_tasks = []
        campaigns_checked = 0
        
        while len(mixed_tasks) < limit and campaigns_checked < len(running_campaign_ids):
            idx = (last_idx + campaigns_checked) % len(running_campaign_ids)
            cid = running_campaign_ids[idx]
            campaigns_checked += 1
            
            task = await self.db.tasks.find_one({
                "campaignId": cid, "status": "pending",
                "$or": [{"deviceId": device_id}, {"deviceId": None}, {"deviceId": ""}]
            }, sort=[("createdAt", 1)])
            
            if not task:
                task = await self.db.tasks.find_one({"campaignId": cid, "status": "pending"}, sort=[("createdAt", 1)])
            
            if task:
                task["_id"] = str(task["_id"])
                mixed_tasks.append(task)
                
        next_idx = (last_idx + campaigns_checked) % max(len(running_campaign_ids), 1)
        await self.db.devices.update_one({"deviceId": device_id}, {"$set": {"lastCampaignIndex": next_idx}})
        
        if mixed_tasks:
            now = datetime.now(timezone.utc).isoformat()
            task_ids = [ObjectId(t["_id"]) for t in mixed_tasks]
            await self.db.tasks.update_many(
                {"_id": {"$in": task_ids}},
                {"$set": {"status": "assigned", "deviceId": device_id, "assignedAt": now, "updatedAt": now}}
            )
        return mixed_tasks

    async def get_logs(self, limit: int, level: str, device_id: str, event_type: str):
        query = {}
        if level: query["level"] = level
        if device_id: query["deviceId"] = device_id
        if event_type: query["eventType"] = event_type
        
        logs = await self.db.activity_logs.find(query).sort("createdAt", -1).limit(limit).to_list(limit)
        for log in logs: log["_id"] = str(log["_id"])
        return logs