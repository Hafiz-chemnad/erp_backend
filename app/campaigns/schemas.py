from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime


class CampaignRecipientIn(BaseModel):
    """One target contact at campaign creation time — starts 'pending'."""
    phone: str


class CampaignStartIn(BaseModel):
    """What Flutter sends the moment 'Launch Campaign' is pressed, BEFORE
    any message actually goes out. This lets the backend track progress
    live as the client's send loop reports back per-recipient outcomes."""
    name: str
    template_name: str
    audience_type: Literal["All", "Label"]
    label_id: Optional[str] = None  # only set when audience_type == "Label"
    recipients: List[CampaignRecipientIn]


class CampaignProgressIn(BaseModel):
    """Sent once per recipient, right after that single WhatsApp send
    attempt completes (success or failure)."""
    phone: str
    outcome: Literal["sent", "failed"]
    error: Optional[str] = None
    wamid: Optional[str] = None


class RecipientOut(BaseModel):
    phone: str
    status: Literal["pending", "sent", "failed"]
    error: Optional[str] = None


class CampaignOut(BaseModel):
    """Response shape. NOTE ON ALIASES: every field below is intentionally
    given the SAME name Dart reads it as — no alias tricks this time. The
    labels module aliased 'id'->'label_id' and 'date'->'created_at', which
    silently broke the Dart client because FastAPI serializes response
    models BY ALIAS by default (so the JSON key becomes the alias, not the
    Python field name). To avoid repeating that bug, this schema keeps
    field name == JSON key == what campaign_api.dart reads, everywhere."""
    campaign_id: str
    name: str
    template_name: str
    audience_type: str
    label_id: Optional[str] = None
    recipients_count: int
    sent_count: int
    delivered_count: int
    read_count: int
    failed_count: int
    status: Literal["sending", "completed", "partial", "failed", "cancelled"]
    recipients: List[RecipientOut] = Field(default_factory=list)
    created_at: Optional[datetime] = None

    class Config:
        populate_by_name = True


class CampaignListItemOut(BaseModel):
    """Lightweight version for the list view — omits the full recipients
    array (could be thousands of entries) since the Campaigns tab only
    needs counts/status for the table. Full recipient detail is fetched
    separately via GET /campaigns/{campaign_id} if/when needed (e.g. a
    future 'retry failed only' screen)."""
    campaign_id: str
    name: str
    template_name: str
    audience_type: str
    label_id: Optional[str] = None
    recipients_count: int
    sent_count: int
    delivered_count: int
    read_count: int
    failed_count: int
    status: str
    created_at: Optional[datetime] = None

    class Config:
        populate_by_name = True


class CampaignListResponse(BaseModel):
    items: List[CampaignListItemOut]
    totalPages: int
    page: int