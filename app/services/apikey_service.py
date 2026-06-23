# app/services/apikey_service.py
import secrets
from datetime import datetime, timezone
from bson import ObjectId
from .base_service import BaseService

class ApiKeyService(BaseService):
    def __init__(self):
        super().__init__()

    async def list_api_keys(self):
        keys = await self.db.api_keys.find().sort("createdAt", -1).to_list(100)
        result = []
        for k in keys:
            k["_id"] = str(k["_id"])
            # Mask the key for display security
            full_key = k.get("key", "")
            k["maskedKey"] = full_key[:8] + "..." + full_key[-4:] if len(full_key) > 12 else full_key
            result.append(k)
        return result

    async def create_api_key(self, data: dict):
        key = f"wak_{secrets.token_hex(32)}"
        
        # Injecting 'scopes' capability for 3rd party integrations
        # Defaults to ["agent"] if no scopes are provided in the request
        scopes = data.get("scopes", ["agent"])

        doc = {
            "name": data.get("name"),
            "description": data.get("description"),
            "key": key,
            "isActive": True,
            "usageCount": 0,
            "scopes": scopes,
            "lastUsedAt": None,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        
        result = await self.db.api_keys.insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        return doc

    async def delete_api_key(self, key_id: str):
        try:
            result = await self.db.api_keys.delete_one({"_id": ObjectId(key_id)})
            return result.deleted_count > 0
        except Exception:
            return False

    async def toggle_api_key(self, key_id: str):
        try:
            key_doc = await self.db.api_keys.find_one({"_id": ObjectId(key_id)})
            if not key_doc:
                return None
                
            new_status = not key_doc.get("isActive", True)
            await self.db.api_keys.update_one(
                {"_id": ObjectId(key_id)},
                {"$set": {"isActive": new_status}}
            )
            return new_status
        except Exception:
            return None

    async def validate_api_key(self, key: str) -> bool:
        """Validates key and tracks usage frequency."""
        key_doc = await self.db.api_keys.find_one({"key": key, "isActive": True})
        if not key_doc:
            return False
            
        await self.db.api_keys.update_one(
            {"_id": key_doc["_id"]},
            {"$set": {"lastUsedAt": datetime.now(timezone.utc).isoformat()}, "$inc": {"usageCount": 1}}
        )
        return True