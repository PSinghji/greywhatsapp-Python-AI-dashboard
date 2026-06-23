"""
API Keys API - Manage authentication keys for Android agents and integrations.
"""
from fastapi import APIRouter, HTTPException
from app.models.schemas import ApiKeyCreate
from app.services.apikey_service import ApiKeyService

router = APIRouter()
apikey_service = ApiKeyService()

@router.get("")
async def list_api_keys():
    """List all API keys (masked)."""
    return await apikey_service.list_api_keys()

@router.post("")
async def create_api_key(data: ApiKeyCreate):
    """Generate a new API key."""
    return await apikey_service.create_api_key(data.model_dump())

@router.delete("/{key_id}")
async def delete_api_key(key_id: str):
    """Delete an API key."""
    success = await apikey_service.delete_api_key(key_id)
    if not success:
        raise HTTPException(status_code=404, detail="API key not found or invalid ID")
    return {"success": True}

@router.post("/{key_id}/toggle")
async def toggle_api_key(key_id: str):
    """Enable/disable an API key."""
    new_status = await apikey_service.toggle_api_key(key_id)
    if new_status is None:
        raise HTTPException(status_code=404, detail="API key not found or invalid ID")
    return {"success": True, "isActive": new_status}

# Utility function for existing agent.py middleware compatibility
async def validate_api_key(key: str) -> bool:
    """Validate an API key and update usage stats."""
    return await apikey_service.validate_api_key(key)