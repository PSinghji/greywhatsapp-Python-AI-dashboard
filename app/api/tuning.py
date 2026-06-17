"""
Tuning Profiles API - Agent behavior configuration.
"""
from fastapi import APIRouter, HTTPException
from bson import ObjectId
from datetime import datetime, timezone

from app.database import get_db
from app.models.schemas import TuningProfileCreate, TuningProfileUpdate

router = APIRouter()


def serialize(doc):
    if doc is None:
        return None
    doc["_id"] = str(doc["_id"])
    return doc


@router.get("")
async def list_profiles():
    """List all tuning profiles."""
    db = get_db()
    profiles = await db.tuning_profiles.find().sort("name", 1).to_list(100)
    return [serialize(p) for p in profiles]


@router.post("")
async def create_profile(data: TuningProfileCreate):
    """Create a new tuning profile."""
    db = get_db()
    existing = await db.tuning_profiles.find_one({"name": data.name})
    if existing:
        raise HTTPException(status_code=409, detail="Profile name already exists")

    profile = data.model_dump()
    profile["isDefault"] = False
    profile["createdAt"] = datetime.now(timezone.utc).isoformat()
    result = await db.tuning_profiles.insert_one(profile)
    profile["_id"] = str(result.inserted_id)
    return profile


@router.get("/{profile_id}")
async def get_profile(profile_id: str):
    """Get a single tuning profile."""
    db = get_db()
    try:
        profile = await db.tuning_profiles.find_one({"_id": ObjectId(profile_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid profile ID")
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return serialize(profile)


@router.put("/{profile_id}")
async def update_profile(profile_id: str, data: TuningProfileUpdate):
    """Update a tuning profile."""
    db = get_db()
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        result = await db.tuning_profiles.update_one(
            {"_id": ObjectId(profile_id)}, {"$set": update_data}
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid profile ID")
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"success": True}


@router.delete("/{profile_id}")
async def delete_profile(profile_id: str):
    """Delete a tuning profile (cannot delete default)."""
    db = get_db()
    try:
        profile = await db.tuning_profiles.find_one({"_id": ObjectId(profile_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid profile ID")
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    if profile.get("isDefault"):
        raise HTTPException(status_code=400, detail="Cannot delete the default profile")
    await db.tuning_profiles.delete_one({"_id": ObjectId(profile_id)})
    return {"success": True}
