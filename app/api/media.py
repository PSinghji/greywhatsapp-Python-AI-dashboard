"""
Media API - Upload and manage campaign media files.
With proper file size validation and clear error messages.
"""
import os
import uuid
import aiofiles
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Request
from bson import ObjectId
from datetime import datetime, timezone

from app.database import get_db

router = APIRouter()

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "application/pdf",
    "video/mp4", "video/3gpp",
}

# File size limits per type (in bytes)
MAX_IMAGE_SIZE = 16 * 1024 * 1024   # 16MB for images (WhatsApp limit)
MAX_VIDEO_SIZE = 50 * 1024 * 1024   # 50MB for videos
MAX_PDF_SIZE = 100 * 1024 * 1024    # 100MB for PDFs
MAX_DEFAULT_SIZE = 50 * 1024 * 1024  # 50MB default


def get_max_size(content_type: str) -> tuple:
    """Return (max_bytes, human_readable_limit) for a content type."""
    if content_type and content_type.startswith("image/"):
        return MAX_IMAGE_SIZE, "16MB"
    elif content_type and content_type.startswith("video/"):
        return MAX_VIDEO_SIZE, "50MB"
    elif content_type == "application/pdf":
        return MAX_PDF_SIZE, "100MB"
    return MAX_DEFAULT_SIZE, "50MB"


def serialize(doc):
    if doc is None:
        return None
    doc["_id"] = str(doc["_id"])
    return doc


@router.get("")
async def list_media(campaignId: str = None):
    """List all uploaded media files."""
    db = get_db()
    query = {}
    if campaignId:
        query["campaignId"] = campaignId
    media = await db.media.find(query).sort("uploadedAt", -1).to_list(500)
    return [serialize(m) for m in media]


@router.post("/upload")
async def upload_media(
    file: UploadFile = File(...),
    campaignId: str = Form(None),
    description: str = Form(""),
):
    """Upload a media file (image, PDF, video) with size validation."""
    # Validate content type
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{file.content_type}' not allowed. Allowed types: {', '.join(sorted(ALLOWED_TYPES))}"
        )

    # Get size limit for this file type
    max_size, max_size_label = get_max_size(file.content_type)

    # Read file content
    content = await file.read()
    file_size = len(content)
    file_size_mb = round(file_size / (1024 * 1024), 2)

    # Validate file size
    if file_size > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {file_size_mb}MB. Maximum allowed for {file.content_type} is {max_size_label}. "
                   f"Please compress or resize the file before uploading."
        )

    if file_size == 0:
        raise HTTPException(status_code=400, detail="File is empty (0 bytes)")

    # Generate unique filename
    ext = os.path.splitext(file.filename)[1] if file.filename else ""
    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_name)

    # Save file
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    # Store metadata in DB
    db = get_db()
    media_doc = {
        "filename": file.filename,
        "storedName": unique_name,
        "contentType": file.content_type,
        "size": file_size,
        "sizeFormatted": f"{file_size_mb}MB",
        "path": file_path,
        "url": f"/uploads/{unique_name}",
        "campaignId": campaignId,
        "description": description,
        "uploadedAt": datetime.now(timezone.utc).isoformat(),
    }
    result = await db.media.insert_one(media_doc)
    media_doc["_id"] = str(result.inserted_id)

    # Log the upload
    try:
        from app.api.agent import log_activity
        await log_activity("media_uploaded",
                           f"Media uploaded: {file.filename} ({file_size_mb}MB)",
                           metadata={"filename": file.filename, "size": file_size,
                                     "contentType": file.content_type, "campaignId": campaignId})
    except Exception:
        pass

    return media_doc


@router.delete("/{media_id}")
async def delete_media(media_id: str):
    """Delete a media file."""
    db = get_db()
    try:
        media = await db.media.find_one({"_id": ObjectId(media_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid media ID")
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    # Delete file from disk
    if os.path.exists(media["path"]):
        os.remove(media["path"])

    await db.media.delete_one({"_id": ObjectId(media_id)})
    return {"success": True}
