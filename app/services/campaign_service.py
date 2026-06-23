# app/services/campaign_service.py
from datetime import datetime, timezone
from bson import ObjectId
import random
import logging
from .base_service import BaseService
from .ai_service import AIService

logger = logging.getLogger(__name__)

class CampaignService(BaseService):
    def __init__(self):
        super().__init__()
        self.ai_service = AIService()

    async def log_activity(self, event_type: str, message: str, device_id: str = None,
                           campaign_id: str = None, task_id: str = None,
                           level: str = "info", metadata: dict = None):
        """Internal service method to log activities."""
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
            logger.error(f"Failed to log activity: {e}")

    async def list_campaigns(self, limit: int = 50, skip: int = 0):
        campaigns = await self.db.campaigns.find().sort("createdAt", -1).skip(skip).limit(limit).to_list(limit)
        campaign_ids = [str(c["_id"]) for c in campaigns]
        
        stats_pipeline = [
            {"$match": {"campaignId": {"$in": campaign_ids}}},
            {"$group": {
                "_id": "$campaignId",
                "sent": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}},
                "failed": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}},
                "pending": {"$sum": {"$cond": [{"$in": ["$status", ["pending", "assigned", "in_progress"]]}, 1, 0]}},
                "invalid": {"$sum": {"$cond": [{"$eq": ["$status", "invalid_number"]}, 1, 0]}},
                "restricted": {"$sum": {"$cond": [{"$eq": ["$status", "account_restricted"]}, 1, 0]}}
            }}
        ]
        
        stats_results = await self.db.tasks.aggregate(stats_pipeline).to_list(None)
        stats_map = {s["_id"]: s for s in stats_results}

        result = []
        for c in campaigns:
            cid = str(c["_id"])
            c["_id"] = cid
            c["stats"] = stats_map.get(cid, {"sent": 0, "failed": 0, "pending": 0, "invalid": 0, "restricted": 0})
            if "_id" in c["stats"]: 
                del c["stats"]["_id"]
            result.append(c)
            
        return result

    async def get_campaign_stats(self):
        return {
            "total": await self.db.campaigns.count_documents({}),
            "active": await self.db.campaigns.count_documents({"status": "running"}),
            "paused": await self.db.campaigns.count_documents({"status": "paused"}),
            "completed": await self.db.campaigns.count_documents({"status": "completed"}),
            "totalSent": await self.db.tasks.count_documents({"status": "completed"}),
            "totalFailed": await self.db.tasks.count_documents({"status": "failed"}),
            "totalPending": await self.db.tasks.count_documents({"status": {"$in": ["pending", "assigned", "in_progress"]}}),
            "totalInvalid": await self.db.tasks.count_documents({"status": "invalid_number"}),
            "totalRestricted": await self.db.tasks.count_documents({"status": "account_restricted"}),
        }

    async def create_campaign(self, data: dict):
        unique_recipients = list(dict.fromkeys(data.get("recipients", [])))
        
        campaign = {
            "name": data.get("name"),
            "description": data.get("description"),
            "status": "draft",
            "recipients": unique_recipients,
            "messages": data.get("messages", []),
            "tuningProfileId": data.get("tuningProfileId"),
            "assignedDevices": data.get("assignedDevices", []),
            "accountType": data.get("accountType"),
            "scheduledAt": data.get("scheduledAt"),
            "aiVariationsEnabled": data.get("aiVariationsEnabled", False),
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
        result = await self.db.campaigns.insert_one(campaign)
        campaign["_id"] = str(result.inserted_id)
        
        await self.log_activity(
            "campaign_created", 
            f"Campaign '{campaign['name']}' created with {len(unique_recipients)} recipients",
            campaign_id=campaign["_id"],
            metadata={"recipientCount": len(unique_recipients), "messageCount": len(campaign["messages"])}
        )
        return campaign

    async def get_campaign_by_id(self, campaign_id: str):
        try:
            return await self.db.campaigns.find_one({"_id": ObjectId(campaign_id)})
        except Exception:
            return None

    async def update_campaign(self, campaign_id: str, update_data: dict):
        try:
            update_data["updatedAt"] = datetime.now(timezone.utc).isoformat()
            return await self.db.campaigns.update_one({"_id": ObjectId(campaign_id)}, {"$set": update_data})
        except Exception:
            return None

    async def delete_campaign(self, campaign_id: str):
        try:
            campaign = await self.db.campaigns.find_one({"_id": ObjectId(campaign_id)})
            result = await self.db.campaigns.delete_one({"_id": ObjectId(campaign_id)})
            if result.deleted_count > 0:
                await self.db.tasks.delete_many({"campaignId": campaign_id})
                await self.log_activity("campaign_deleted", f"Campaign '{campaign.get('name', campaign_id)}' deleted", campaign_id=campaign_id, level="warning")
            return result
        except Exception:
            return None

    async def start_campaign(self, campaign_id: str):
        campaign = await self.get_campaign_by_id(campaign_id)
        if not campaign:
            return "not_found"
        if not campaign.get("recipients") or not campaign.get("messages"):
            return "missing_data"

        assigned_devices = campaign.get("assignedDevices", [])
        all_devices = await self.db.devices.find({"status": {"$nin": ["restricted", "blocked"]}}).to_list(None)
        all_device_ids = [d["deviceId"] for d in all_devices]
        
        if not assigned_devices:
            assigned_devices = all_device_ids
            if not assigned_devices:
                return "no_devices"

        # Wake-up logic
        now = datetime.now(timezone.utc).isoformat()
        wake_up_count = 0
        woken_device_ids = []
        for device_id in assigned_devices:
            result = await self.db.devices.update_one(
                {"deviceId": device_id},
                {"$set": {"pendingCommand": "wake_up", "updatedAt": now}}
            )
            if result.modified_count > 0 or result.matched_count > 0:
                wake_up_count += 1
                woken_device_ids.append(device_id)
        
        for did in woken_device_ids:
            await self.log_activity("wake_up_sent", f"Wake-up sent to {did}", device_id=did, campaign_id=campaign_id)

        # Tuning profile logic
        tuning = None
        if campaign.get("tuningProfileId"):
            try:
                tuning = await self.db.tuning_profiles.find_one({"_id": ObjectId(campaign["tuningProfileId"])})
            except Exception:
                pass
        if not tuning:
            tuning = await self.db.tuning_profiles.find_one({"isDefault": True})

        tuning_data = {k: v for k, v in (tuning or {}).items() if k not in ["_id", "name", "description", "isDefault"]}
        tuning_data.setdefault("betweenRecipientsMin", 8000)
        tuning_data.setdefault("betweenRecipientsMax", 20000)
        tuning_data.setdefault("messageDelayMin", 3000)
        tuning_data.setdefault("messageDelayMax", 8000)

        # ═══ AI VARIATION GENERATOR ═══
        messages = campaign["messages"]
        if campaign.get("aiVariationsEnabled") and messages:
            logger.info(f"[Campaign {campaign_id}] AI Variations Enabled. Generating rewritten messages...")
            expanded_messages = []
            for base_msg in messages:
                # Ask AI for 3 variations of each original message
                variations = await self.ai_service.generate_message_variations(base_msg, count=3)
                expanded_messages.extend(variations)
            
            # Replace the standard messages with our massive new pool of AI variations
            if expanded_messages:
                messages = expanded_messages

        # Task creation
        tasks = []
        for recipient in campaign["recipients"]:
            # Uses the newly expanded AI messages array if variations were enabled!
            message = random.choice(messages) if len(messages) > 1 else messages[0]
            tasks.append({
                "campaignId": str(campaign["_id"]),
                "campaignName": campaign["name"],
                "deviceId": None,  # Dynamic round-robin
                "recipient": recipient,
                "message": message,
                "tuning": tuning_data,
                "accountType": campaign.get("accountType"),
                "status": "pending",
                "retryCount": 0,
                "maxRetries": tuning_data.get("maxRetries", 3),
                "createdAt": now,
                "updatedAt": now,
                "assignedAt": None,
                "errorMessage": None,
                "deliveredAt": None,
            })

        if tasks:
            random.shuffle(tasks)
            await self.db.tasks.insert_many(tasks)

        await self.db.campaigns.update_one(
            {"_id": ObjectId(campaign_id)},
            {"$set": {"status": "running", "assignedDevices": assigned_devices, "startedAt": now, "updatedAt": now}}
        )

        await self.log_activity("campaign_started", f"Campaign started: {len(tasks)} tasks", campaign_id=campaign_id)
        return {"tasksCreated": len(tasks), "devicesAssigned": len(assigned_devices), "wakeUpsSent": wake_up_count}
    
    async def update_campaign_status(self, campaign_id: str, current_status: str, new_status: str, action_name: str):
        """Helper for pause, resume, and stop."""
        try:
            now = datetime.now(timezone.utc).isoformat()
            update_fields = {"status": new_status, "updatedAt": now}
            if new_status == "stopped":
                update_fields["stoppedAt"] = now

            result = await self.db.campaigns.update_one(
                {"_id": ObjectId(campaign_id), "status": current_status} if current_status else {"_id": ObjectId(campaign_id)},
                {"$set": update_fields}
            )
            
            if result.matched_count == 0:
                return False

            if new_status == "stopped":
                await self.db.tasks.update_many(
                    {"campaignId": campaign_id, "status": {"$in": ["pending", "assigned"]}},
                    {"$set": {"status": "failed", "errorMessage": "Campaign stopped", "updatedAt": now}}
                )

            await self.log_activity(f"campaign_{action_name}", f"Campaign {campaign_id} {action_name}", campaign_id=campaign_id)
            return True
        except Exception:
            return False

    async def retry_failed_tasks(self, campaign_id: str):
        now = datetime.now(timezone.utc).isoformat()
        campaign = await self.get_campaign_by_id(campaign_id)
        if not campaign or not campaign.get("messages"):
            return None

        result = await self.db.tasks.update_many(
            {"campaignId": campaign_id, "status": "failed"},
            {"$set": {
                "status": "pending",
                "message": campaign["messages"][0],
                "updatedAt": now,
                "retryCount": 0,
                "errorMessage": None,
                "deviceId": None,  # Shuffle
                "assignedAt": None,
            }}
        )

        if campaign['status'] in ['completed', 'stopped']:
            await self.db.campaigns.update_one({"_id": ObjectId(campaign_id)}, {"$set": {"status": "running", "updatedAt": now}})

        await self.log_activity("campaign_retried", f"Retrying {result.modified_count} tasks", campaign_id=campaign_id)
        return result.modified_count

    async def get_campaign_report(self, campaign_id: str):
        campaign = await self.get_campaign_by_id(campaign_id)
        if not campaign:
            return None

        pipeline = [
            {"$match": {"campaignId": campaign_id}},
            {"$sort": {"updatedAt": -1}},
            {"$group": {"_id": "$recipient", "latest_task": {"$first": "$$ROOT"}}},
            {"$replaceRoot": {"newRoot": "$latest_task"}},
            {"$lookup": {"from": "devices", "localField": "deviceId", "foreignField": "deviceId", "as": "device_info"}},
            {"$addFields": {
                "assignedDeviceId": "$deviceId",
                "assignedDeviceName": {"$ifNull": [{"$arrayElemAt": ["$device_info.deviceName", 0]}, "$deviceId"]},
                "assignedDevicePhone": {"$ifNull": [{"$arrayElemAt": ["$device_info.phoneNumber", 0]}, None]},
                "failureReason": "$errorMessage"
            }},
            {"$project": {"device_info": 0}},
            {"$sort": {"status": 1, "updatedAt": -1}}
        ]

        tasks = await self.db.tasks.aggregate(pipeline).to_list(None)
        
        stats = {
            "total": len(tasks),
            "completed": sum(1 for t in tasks if t.get("status") == "completed"),
            "failed": sum(1 for t in tasks if t.get("status") == "failed"),
            "invalid_number": sum(1 for t in tasks if t.get("status") == "invalid_number"),
            "account_restricted": sum(1 for t in tasks if t.get("status") == "account_restricted"),
            "pending": sum(1 for t in tasks if t.get("status") in ["pending", "assigned", "in_progress"]),
        }

        return {
            "campaign": {
                "_id": str(campaign["_id"]),
                "name": campaign.get("name", ""),
                "status": campaign.get("status", ""),
                "accountType": campaign.get("accountType"),
            },
            "stats": stats,
            "tasks": tasks
        }