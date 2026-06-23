"""
Campaigns API v2 - Create and manage message campaigns.

MAJOR CHANGES:
1. Wake-up signal: On campaign start, sends pendingCommand="wake_up" to all assigned devices
2. Dynamic task assignment: Tasks created WITHOUT deviceId - assigned dynamically by round-robin
3. Multi-media support: Campaigns can have up to 4 media items (2 images + 1 PDF + 1 video)
4. Retry with device shuffling: Failed tasks get reassigned to different devices
5. Anti-blocking: Increased default timing gaps
"""
from fastapi import APIRouter, HTTPException, Depends, Security
from app.models.schemas import CampaignCreate, CampaignUpdate
from app.services.campaign_service import CampaignService
from app.services.auth_service import AuthService, RequireScope
router = APIRouter()
campaign_service = CampaignService()

def serialize(doc):
    if doc: doc["_id"] = str(doc["_id"])
    return doc

@router.get("")
async def list_campaigns(limit: int = 50, skip: int = 0):
    """List campaigns with pagination and injected stats."""
    return await campaign_service.list_campaigns(limit, skip)

@router.get("/stats")
async def campaign_stats(
    api_key_data: dict = Depends(AuthService.verify_api_key)
):
    """Get overall campaign statistics."""
    # We now know the user is authenticated!
    return await campaign_service.get_campaign_stats()

@router.post("")
async def create_campaign(
    data: CampaignCreate,
    api_key_data: dict = Security(RequireScope("campaigns:write"))
):
    """Create a new campaign. Requires 'campaigns:write' scope."""
    campaign_dict = data.model_dump()
    return await campaign_service.create_campaign(campaign_dict)

@router.get("/{campaign_id}")
async def get_campaign(campaign_id: str):
    """Get a single campaign."""
    campaign = await campaign_service.get_campaign_by_id(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found or invalid ID")
    return serialize(campaign)

@router.put("/{campaign_id}")
async def update_campaign(campaign_id: str, data: CampaignUpdate):
    """Update a campaign."""
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
        
    result = await campaign_service.update_campaign(campaign_id, update_data)
    if not result or result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Campaign not found or invalid ID")
    return {"success": True}

@router.delete("/{campaign_id}")
async def delete_campaign(campaign_id: str):
    """Delete a campaign and its tasks."""
    result = await campaign_service.delete_campaign(campaign_id)
    if not result or result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Campaign not found or invalid ID")
    return {"success": True}

@router.post("/{campaign_id}/start")
async def start_campaign(campaign_id: str):
    """Start a campaign - generate tasks and send wake-up to devices."""
    result = await campaign_service.start_campaign(campaign_id)
    
    if result == "invalid_id":
        raise HTTPException(status_code=400, detail="Invalid campaign ID")
    elif result == "not_found":
        raise HTTPException(status_code=404, detail="Campaign not found")
    elif result == "missing_data":
        raise HTTPException(status_code=400, detail="No recipients or messages in campaign")
    elif result == "no_devices":
        raise HTTPException(status_code=400, detail="No available devices")
        
    result["success"] = True
    return result

@router.post("/{campaign_id}/pause")
async def pause_campaign(campaign_id: str):
    """Pause a running campaign."""
    success = await campaign_service.update_campaign_status(campaign_id, "running", "paused", "paused")
    if not success:
        raise HTTPException(status_code=404, detail="Campaign not found or not running")
    return {"success": True}

@router.post("/{campaign_id}/resume")
async def resume_campaign(campaign_id: str):
    """Resume a paused campaign."""
    success = await campaign_service.update_campaign_status(campaign_id, "paused", "running", "resumed")
    if not success:
        raise HTTPException(status_code=404, detail="Campaign not found or not paused")
    return {"success": True}

@router.post("/{campaign_id}/stop")
async def stop_campaign(campaign_id: str):
    """Stop a campaign and cancel pending tasks."""
    success = await campaign_service.update_campaign_status(campaign_id, None, "stopped", "stopped")
    if not success:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {"success": True}

@router.post("/{campaign_id}/retry")
async def retry_failed_tasks(campaign_id: str):
    """Retry all failed tasks for a campaign with device shuffling."""
    retried_count = await campaign_service.retry_failed_tasks(campaign_id)
    if retried_count is None:
        raise HTTPException(status_code=404, detail="Campaign not found or missing messages")
    return {"success": True, "retriedTasks": retried_count}

@router.get("/{campaign_id}/report")
@router.get("/{campaign_id}/details")
async def get_campaign_report(campaign_id: str):
    """Get a detailed report for a single campaign with device info."""
    data = await campaign_service.get_campaign_report(campaign_id)
    if not data:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    # Serialize IDs for JSON response
    for task in data["tasks"]:
        task["_id"] = str(task.get("_id"))
        
    return data