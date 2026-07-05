from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class MenuItemIn(BaseModel):
    """What the Flutter app sends when creating/updating an item."""
    retailer_id: str
    name: str
    price: float = 0.0
    category: str = "Menu Item"
    image_url: str = ""
    is_available: bool = True
    is_veg: bool = False


class MenuItemOut(BaseModel):
    """What the API returns — matches the field names your MenuDbService.upsertMenuItem
    already reads (id/retailerId/name/price/category/imageUrl/isAvailable/isVeg)."""
    id: str = Field(alias="retailer_id")
    retailerId: str = Field(alias="retailer_id")
    name: str
    price: float
    category: str
    imageUrl: str = Field(alias="image_url")
    isAvailable: bool = Field(alias="is_available")
    isVeg: bool = Field(alias="is_veg")
    updatedAt: Optional[datetime] = Field(default=None, alias="updated_at")

    class Config:
        populate_by_name = True


class MenuListResponse(BaseModel):
    items: list[MenuItemOut]
    totalPages: int
    page: int


class MetaCredentials(BaseModel):
    """Optional Meta credentials attached to a write request.
    Sent by Flutter on every call — never stored server-side (see
    Phase 1 design decision: backend doesn't own restaurant settings)."""
    catalog_id: Optional[str] = None
    access_token: Optional[str] = None


class MenuItemWrite(MenuItemIn, MetaCredentials):
    """Body for create/update — menu fields + optional Meta credentials."""
    pass


class MenuItemUpdateFields(MetaCredentials):
    """Body for PUT (partial update / toggle) — arbitrary fields dict +
    optional Meta credentials. `fields` holds whatever columns changed."""
    fields: dict


class MetaSyncRequest(BaseModel):
    """Body for POST /sync-meta — credentials are required here, not optional."""
    catalog_id: str
    access_token: str


class MetaSyncResponse(BaseModel):
    synced_count: int