from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class ContactIn(BaseModel):
    """What Flutter sends for a single Add Contact. phone is the identity
    key (digits only, country code included — matches current app's
    RegExp(r'[^0-9]') stripping before send)."""
    phone: str
    name: str
    status: str = "Active"


class ContactBulkRow(BaseModel):
    """One row from a parsed CSV — name may be empty (falls back to phone,
    same as today's Flutter behaviour)."""
    phone: str
    name: str = ""


class ContactBulkIn(BaseModel):
    rows: List[ContactBulkRow]


class ContactLabelsUpdate(BaseModel):
    """Body for PUT .../labels — full replacement list of label_ids,
    since apply/remove in the UI both resolve to 'here is the new set'."""
    label_ids: List[str]


class ContactOut(BaseModel):
    """Matches what contacts_tab.dart expects: phone/name/status/labels(+ids)"""
    phone: str
    name: str
    status: str
    label_ids: List[str] = Field(default_factory=list)
    source: str = "manual"
    date: Optional[datetime] = Field(default=None, alias="created_at")

    class Config:
        populate_by_name = True


class ContactListResponse(BaseModel):
    items: List[ContactOut]
    totalPages: int
    page: int


class ContactBulkResult(BaseModel):
    added: int
    enriched: int
    duplicate: int
    invalid: int