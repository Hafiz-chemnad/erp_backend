from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class TemplateButton(BaseModel):
    type: str
    text: str
    url: Optional[str] = None
    phone_number: Optional[str] = None


class TemplateCreateIn(BaseModel):
    waba_id: str
    access_token: str
    name: str
    category: str
    language: str
    body_text: str
    header_type: str = "NONE"
    header_text: Optional[str] = None
    buttons: Optional[List[TemplateButton]] = None


class RefreshStatusIn(BaseModel):
    waba_id: str
    access_token: str


# 🚀 NEW: body for PATCH /templates/{name}/mapping — this endpoint didn't
# exist before, which meant variable mapping choices only ever got saved
# to local SQLite and were lost on reinstall/second device.
class VariableMappingUpdateRequest(BaseModel):
    variable_mapping: Dict[str, Any]


class TemplateOut(BaseModel):
    template_id: str
    restaurant_id: str
    name: str
    category: str
    language: str
    body_text: str
    variable_count: int
    status: str
    rejected_reason: Optional[str] = None
    default_mappings: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    header_type: str = "NONE"
    header_text: Optional[str] = None
    buttons: Optional[List[Dict[str, Any]]] = None

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
    media_id: str | None = None
    button_url_param: str | None = None