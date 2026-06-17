"""
API Keys API - Manage authentication keys for Android agents.
"""
import secrets
from fastapi import APIRouter, HTTPException
from bson import ObjectId
from datetime import datetime, timezone

from app.database import get_db
from app.models.schemas import ApiKeyCreate

router = APIRouter()


def serialize(doc):
    if doc is None:
        return None
    doc["_id"] = str(doc["_id"])
    return doc


@router.get("")
async def list_api_keys():
    """List all API keys (masked)."""
    db = get_db()
    keys = await db.api_keys.find().sort("createdAt", -1).to_list(100)
    result = []
    for k in keys:
        k["_id"] = str(k["_id"])
        # Mask the key for display
        full_key = k.get("key", "")
        k["maskedKey"] = full_key[:8] + "..." + full_key[-4:] if len(full_key) > 12 else full_key
        result.append(k)
    return result


@router.post("")
async def create_api_key(data: ApiKeyCreate):
    """Generate a new API key."""
    db = get_db()
    key = f"wak_{secrets.token_hex(32)}"
    doc = {
        "name": data.name,
        "description": data.description,
        "key": key,
        "isActive": True,
        "usageCount": 0,
        "lastUsedAt": None,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    result = await db.api_keys.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


@router.delete("/{key_id}")
async def delete_api_key(key_id: str):
    """Delete an API key."""
    db = get_db()
    try:
        result = await db.api_keys.delete_one({"_id": ObjectId(key_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid key ID")
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"success": True}


@router.post("/{key_id}/toggle")
async def toggle_api_key(key_id: str):
    """Enable/disable an API key."""
    db = get_db()
    try:
        key_doc = await db.api_keys.find_one({"_id": ObjectId(key_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid key ID")
    if not key_doc:
        raise HTTPException(status_code=404, detail="API key not found")
    new_status = not key_doc.get("isActive", True)
    await db.api_keys.update_one(
        {"_id": ObjectId(key_id)},
        {"$set": {"isActive": new_status}}
    )
    return {"success": True, "isActive": new_status}


async def validate_api_key(key: str) -> bool:
    """Validate an API key and update usage stats."""
    db = get_db()
    key_doc = await db.api_keys.find_one({"key": key, "isActive": True})
    if not key_doc:
        return False
    await db.api_keys.update_one(
        {"_id": key_doc["_id"]},
        {"$set": {"lastUsedAt": datetime.now(timezone.utc).isoformat()}, "$inc": {"usageCount": 1}}
    )
    return True
