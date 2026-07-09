from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class TemplateCreateIn(BaseModel):
    waba_id: str
    access_token: str
    name: str
    category: str  # MARKETING, UTILITY
    language: str  # e.g., en_US
    body_text: str
    header_type: str = "NONE"  # NONE, TEXT, IMAGE, VIDEO, DOCUMENT
    header_text: Optional[str] = None

class RefreshStatusIn(BaseModel):
    waba_id: str
    access_token: str

class TemplateOut(BaseModel):
    template_id: str
    restaurant_id: str
    name: str
    category: str
    language: str
    body_text: str
    variable_count: int
    status: str  # APPROVED, PENDING, REJECTED
    rejected_reason: Optional[str] = None
    default_mappings: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    header_type: str = "NONE"
    header_text: Optional[str] = None

    class Config:
        populate_by_name = True

class TemplateListResponse(BaseModel):
    items: List[TemplateOut]

class SendMessageRequest(BaseModel):
    phone_number_id: str 
    access_token: str
    to_phone: str
    template_name: str
    language_code: str = "en_US"
    body_params: list[str] = []
    header_type: str = "NONE"
    media_url: str | None = None    