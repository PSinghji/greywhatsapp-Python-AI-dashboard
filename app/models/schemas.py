"""
Pydantic models for request/response validation.
v3: Added 1024-character auto-truncation for campaign text/caption.
    Added multi-media support (up to 4 media items per campaign message).
    Added MediaItem model for structured media handling.
    All original classes preserved for backward compatibility.
"""
from pydantic import BaseModel, Field, model_validator, field_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ─── Constants ──────────────────────────────────────────
MAX_TEXT_LENGTH = 1024  # WhatsApp-safe text limit


# ─── Enums ───────────────────────────────────────────────
class DeviceStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"
    PAUSED = "paused"
    RESTRICTED = "restricted"
    BLOCKED = "blocked"


class CampaignStatus(str, Enum):
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    STOPPED = "stopped"


class TaskStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    INVALID_NUMBER = "invalid_number"
    ACCOUNT_RESTRICTED = "account_restricted"
    ACCOUNT_BLOCKED = "account_blocked"


class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    PDF = "pdf"
    VIDEO = "video"
    MULTI_MEDIA = "multi_media"


class MediaType(str, Enum):
    """Media types for multi-media campaigns."""
    IMAGE = "image"
    PDF = "pdf"
    VIDEO = "video"


class WhatsappAccountType(str, Enum):
    PERSONAL = "personal"
    BUSINESS = "business"


# ─── Device Models ───────────────────────────────────────
class DeviceRegister(BaseModel):
    deviceId: str
    deviceName: Optional[str] = None
    phoneNumber: Optional[str] = None
    androidVersion: Optional[str] = None
    model: Optional[str] = None
    appVersion: Optional[str] = None
    whatsappAccountType: Optional[WhatsappAccountType] = WhatsappAccountType.PERSONAL


class DeviceUpdate(BaseModel):
    deviceName: Optional[str] = None
    phoneNumber: Optional[str] = None
    status: Optional[DeviceStatus] = None
    whatsappAccountType: Optional[WhatsappAccountType] = None


class DeviceHeartbeat(BaseModel):
    deviceId: str
    batteryLevel: int = Field(ge=0, le=100)
    isCharging: bool = False
    wifiConnected: bool = False
    mobileData: bool = False
    whatsappInstalled: bool = True
    freeMemoryMB: Optional[int] = None
    activeTaskId: Optional[str] = None
    tasksSentCount: int = 0
    tasksFailedCount: int = 0
    # New fields for dual WhatsApp and restriction detection
    deviceName: Optional[str] = None
    phoneNumber: Optional[str] = None
    accountStatus: Optional[str] = None  # "active", "restricted", "blocked"
    personalEnabled: Optional[bool] = None
    businessEnabled: Optional[bool] = None
    personalPhone: Optional[str] = None
    businessPhone: Optional[str] = None


# ─── Media Item Model (for multi-media campaigns) ───────
class MediaItem(BaseModel):
    """A single media attachment in a multi-media campaign.
    Max per campaign: 2 images, 1 PDF, 1 video (4 total).
    """
    type: MediaType
    url: str  # CDN/S3 URL of the media file
    name: Optional[str] = None  # Original filename
    caption: Optional[str] = None  # Caption for this media item

    @field_validator('caption', mode='before')
    @classmethod
    def truncate_caption(cls, v):
        """Auto-truncate caption to MAX_TEXT_LENGTH characters."""
        if v and isinstance(v, str) and len(v) > MAX_TEXT_LENGTH:
            return v[:MAX_TEXT_LENGTH]
        return v


# ─── Campaign Models ────────────────────────────────────
class MessageTemplate(BaseModel):
    """Message template supporting both legacy single-media and new multi-media.
    
    Legacy mode: type + content + mediaUrl
    Multi-media mode: content (text) + mediaItems[] (up to 4)
    
    Text is associated with the FIRST media item when sent.
    
    v3: content and caption are auto-truncated to 1024 characters.
    """
    type: MessageType = MessageType.TEXT
    content: str = ""
    mediaUrl: Optional[str] = None
    mediaName: Optional[str] = None
    caption: Optional[str] = None
    buttons: Optional[List[str]] = None
    # NEW: Multi-media support
    mediaItems: Optional[List[MediaItem]] = None

    @field_validator('content', mode='before')
    @classmethod
    def truncate_content(cls, v):
        """Auto-truncate content to MAX_TEXT_LENGTH characters."""
        if v and isinstance(v, str) and len(v) > MAX_TEXT_LENGTH:
            return v[:MAX_TEXT_LENGTH]
        return v

    @field_validator('caption', mode='before')
    @classmethod
    def truncate_caption(cls, v):
        """Auto-truncate caption to MAX_TEXT_LENGTH characters."""
        if v and isinstance(v, str) and len(v) > MAX_TEXT_LENGTH:
            return v[:MAX_TEXT_LENGTH]
        return v

    @model_validator(mode='after')
    def validate_media_limits(self):
        """Validate multi-media limits: max 2 images, 1 PDF, 1 video."""
        if self.mediaItems:
            image_count = sum(1 for m in self.mediaItems if m.type == MediaType.IMAGE)
            pdf_count = sum(1 for m in self.mediaItems if m.type == MediaType.PDF)
            video_count = sum(1 for m in self.mediaItems if m.type == MediaType.VIDEO)
            
            if image_count > 2:
                raise ValueError("Maximum 2 images allowed per message")
            if pdf_count > 1:
                raise ValueError("Maximum 1 PDF allowed per message")
            if video_count > 1:
                raise ValueError("Maximum 1 video allowed per message")
            if len(self.mediaItems) > 4:
                raise ValueError("Maximum 4 media items allowed per message")
        return self


class CampaignCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    recipients: List[str] = []
    messages: List[MessageTemplate] = []
    tuningProfileId: Optional[str] = None
    assignedDevices: List[str] = []
    scheduledAt: Optional[str] = None
    accountType: Optional[str] = None  # "personal" or "business" for dual WhatsApp routing
    aiVariationsEnabled: bool = False

class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[CampaignStatus] = None
    recipients: Optional[List[str]] = None
    messages: Optional[List[MessageTemplate]] = None
    tuningProfileId: Optional[str] = None
    assignedDevices: Optional[List[str]] = None
    accountType: Optional[str] = None
    aiVariationsEnabled: Optional[bool] = None

# ─── Task Models ─────────────────────────────────────────
class TaskComplete(BaseModel):
    taskId: str
    deviceId: str
    status: TaskStatus
    errorMessage: Optional[str] = None
    deliveredAt: Optional[str] = None


# ─── Step Log Model ──────────────────────────────────────
class StepLog(BaseModel):
    deviceId: str
    taskId: Optional[str] = None
    step: str
    status: str = "info"  # "start", "success", "fail", "retry", "info"
    message: str = ""
    metadata: Optional[dict] = None


# ─── Tuning Profile Models ──────────────────────────────
class TuningProfileCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    typingSpeedMin: int = Field(default=30, ge=10, le=500)
    typingSpeedMax: int = Field(default=80, ge=20, le=1000)
    messageDelayMin: int = Field(default=2000, ge=500)
    messageDelayMax: int = Field(default=5000, ge=1000)
    betweenRecipientsMin: int = Field(default=5000, ge=1000)
    betweenRecipientsMax: int = Field(default=15000, ge=2000)
    typingMistakesEnabled: bool = True
    typingMistakesRate: float = Field(default=0.02, ge=0, le=0.2)
    randomPausesEnabled: bool = True
    randomPauseChance: float = Field(default=0.10, ge=0, le=0.5)
    randomPauseMin: int = Field(default=500, ge=100)
    randomPauseMax: int = Field(default=2000, ge=200)
    maxRetries: int = Field(default=3, ge=1, le=10)


class TuningProfileUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    typingSpeedMin: Optional[int] = None
    typingSpeedMax: Optional[int] = None
    messageDelayMin: Optional[int] = None
    messageDelayMax: Optional[int] = None
    betweenRecipientsMin: Optional[int] = None
    betweenRecipientsMax: Optional[int] = None
    typingMistakesEnabled: Optional[bool] = None
    typingMistakesRate: Optional[float] = None
    randomPausesEnabled: Optional[bool] = None
    randomPauseChance: Optional[float] = None
    randomPauseMin: Optional[int] = None
    randomPauseMax: Optional[int] = None
    maxRetries: Optional[int] = None


# ─── API Key Models ──────────────────────────────────────
class ApiKeyCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    # Add the scopes field to support our new authentication service!
    scopes: Optional[List[str]] = ["agent"]


# ─── Agent Task Fetch ────────────────────────────────────
class AgentTaskFetch(BaseModel):
    deviceId: str
    limit: int = Field(default=5, ge=1, le=20)


# ─── Config Sync Model ──────────────────────────────────
class ConfigSync(BaseModel):
    deviceId: str
    deviceName: Optional[str] = None
    personalEnabled: Optional[bool] = None
    personalPhone: Optional[str] = None
    businessEnabled: Optional[bool] = None
    businessPhone: Optional[str] = None
    autoStart: Optional[bool] = None
