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

    class Config:
        populate_by_name = True

class TemplateListResponse(BaseModel):
    items: List[TemplateOut]