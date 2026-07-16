from pydantic import BaseModel
from typing import Any


class AssignOrderRequest(BaseModel):
    delivery_boy_phone: str
    delivery_boy_name: str
    order_snapshot: dict[str, Any]   # items, total, customerNumber, location, displayId — whatever you already have client-side


class AssignmentOut(BaseModel):
    id: str
    restaurant_id: str
    order_id: str
    display_id: str
    delivery_boy_phone: str
    delivery_boy_name: str
    customer_number: str
    delivery_status: str
    order_snapshot: dict[str, Any]
    assigned_at: str