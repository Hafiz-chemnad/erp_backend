from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime


class CampaignRecipientIn(BaseModel):
    """One target contact at campaign creation time — starts 'pending'."""
    phone: str


class CampaignStartIn(BaseModel):
    """What Flutter sends the moment 'Launch Campaign' is pressed, BEFORE
    any message actually goes out."""
    name: str
    template_name: str
    audience_type: Literal["All", "Label"]
    label_id: Optional[str] = None
    recipients: List[CampaignRecipientIn]
    # 🚀 FIX: persist media/button choices with the campaign record so a
    # later Resume doesn't force the user to re-upload the same asset.
    media_id: Optional[str] = None
    media_url: Optional[str] = None
    button_url_param: Optional[str] = None


class CampaignProgressIn(BaseModel):
    phone: str
    outcome: Literal["pending", "sent", "failed"]
    error: Optional[str] = None
    wamid: Optional[str] = None


class RecipientOut(BaseModel):
    """🚀 FIX: status was Literal["pending","sent","failed"] — the webhook
    writes 'delivered'/'read' straight into Mongo with no validation, so
    the FIRST time any recipient reached one of those states, every read
    of this campaign (GET detail, report_progress's own return value)
    crashed with a Pydantic validation error. Also added 'wamid', which
    was being written by the webhook/progress handlers but silently
    dropped on every read since it wasn't declared here."""
    phone: str
    status: Literal["pending", "sent", "delivered", "read", "failed"]
    error: Optional[str] = None
    wamid: Optional[str] = None


class CampaignOut(BaseModel):
    """Response shape. Field names intentionally match Dart's reads
    exactly — no alias tricks (see labels module for why that matters)."""
    campaign_id: str
    name: str
    template_name: str
    audience_type: str
    label_id: Optional[str] = None
    recipients_count: int
    sent_count: int
    delivered_count: int = 0
    read_count: int = 0
    failed_count: int
    status: Literal["sending", "completed", "partial", "failed", "cancelled"]
    recipients: List[RecipientOut] = Field(default_factory=list)
    media_id: Optional[str] = None
    media_url: Optional[str] = None
    button_url_param: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        populate_by_name = True


class CampaignListItemOut(BaseModel):
    """Lightweight version for the list view — omits recipients array."""
    campaign_id: str
    name: str
    template_name: str
    audience_type: str
    label_id: Optional[str] = None
    recipients_count: int
    sent_count: int
    delivered_count: int = 0
    read_count: int = 0
    failed_count: int
    status: str
    created_at: Optional[datetime] = None

    class Config:
        populate_by_name = True


class CampaignListResponse(BaseModel):
    items: List[CampaignListItemOut]
    totalPages: int
    page: int