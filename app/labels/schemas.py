from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class LabelIn(BaseModel):
    """What Flutter sends when creating a label. label_id is generated
    client-side (matches existing pattern: 'lbl_<timestamp>') and passed in."""
    label_id: str
    name: str
    description: str = "No description"
    is_automated: bool = False


class LabelUpdate(BaseModel):
    """Body for PUT (rename/edit) — is_automated labels reject this at the
    router level, same rule as the current Flutter-side check."""
    name: str
    description: str = "No description"


class LabelOut(BaseModel):
    """Matches what labels_tab.dart already expects: id/name/description/count/is_automated/date"""
    id: str = Field(alias="label_id")
    name: str
    description: str
    count: int = Field(alias="contact_count")
    is_automated: bool
    date: Optional[datetime] = Field(default=None, alias="created_at")

    class Config:
        populate_by_name = True


class LabelListResponse(BaseModel):
    items: list[LabelOut]
    totalPages: int
    page: int