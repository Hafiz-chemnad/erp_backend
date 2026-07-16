from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class DeliveryBoyIn(BaseModel):
    """What Flutter sends when adding a delivery boy."""
    name: str
    phone: str  # unique per restaurant — this is the identity key (no Mongo _id exposed)


class DeliveryBoyOut(BaseModel):
    """Matches the shape OrderDbService.getAllDeliveryBoys already returns
    (id/name/phone as strings) — here 'id' is just the phone number, since
    that's the natural unique key, not an autoincrement int like local SQLite uses."""
    id: str = Field(alias="phone")
    name: str
    phone: str
    createdAt: Optional[datetime] = Field(default=None, alias="created_at")

    class Config:
        populate_by_name = True


class DeliveryBoyUpdate(BaseModel):
    """Body for PUT — only the name is editable; phone is the identity key
    and stays fixed in the URL path."""
    name: str


class DeliveryBoyListResponse(BaseModel):
    items: list[DeliveryBoyOut]
    totalPages: int
    page: int