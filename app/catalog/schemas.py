from pydantic import BaseModel
from typing import Optional


class CatalogItem(BaseModel):
    retailer_id: str
    name: str
    price: float
    availability: str = "in stock"
    image_url: Optional[str] = None


class CatalogLinkIn(BaseModel):
    restaurantId: str
    catalogId: str


class SendProductIn(BaseModel):
    restaurantId: str
    customerNumber: str
    phoneNumberId: str
    retailerId: str


class SendMenuIn(BaseModel):
    restaurantId: str
    customerNumber: str
    phoneNumberId: str