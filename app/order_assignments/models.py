from pydantic import BaseModel
from typing import Any, Optional


class AssignOrderRequest(BaseModel):
    delivery_boy_phone: str
    delivery_boy_name: str
    order_snapshot: dict[str, Any]


class UpdateAssignmentStatusRequest(BaseModel):
    status: str          # 'db_accepted' | 'picked_up' | 'delivered'
    payment_method: Optional[str] = None   # 'cash' | 'gpay' — only for 'delivered'
    send_customer_message: bool = True     # optional toggle, per your original plan


class AssignmentOut(BaseModel):
    id: str
    restaurant_id: str
    order_id: str
    display_id: str
    delivery_boy_phone: str
    delivery_boy_name: str
    customer_number: str
    delivery_status: str
    payment_method: str | None = None
    order_snapshot: dict[str, Any]
    assigned_at: str
    accepted_at: str | None = None
    picked_up_at: str | None = None
    delivered_at: str | None = None