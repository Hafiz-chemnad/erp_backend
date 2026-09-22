from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class OrderItem(BaseModel):
    name: str
    qty: int
    price: float


class LocationOut(BaseModel):
    lat: float
    lng: float


class OrderOut(BaseModel):
    orderId: str
    customerNumber: Optional[str] = None
    items: list[OrderItem]
    totalAmount: float
    paymentStatus: str  # pending | accepted | preparing | ready | completed | rejected | assigned
    orderType: Optional[str] = None  # DELIVERY | TAKEAWAY (WhatsApp orders only)
    restaurantId: str
    restaurantName: str
    location: Optional[LocationOut] = None
    additionalNotes: Optional[str] = None
    createdAt: datetime

    # ── Billing/POS fields (absent on existing WhatsApp orders) ──────────
    source: Optional[str] = "whatsapp"       # whatsapp | pos
    orderMode: Optional[str] = None          # dine_in | takeaway_counter | phone
    tableNumber: Optional[str] = None
    billedBy: Optional[str] = None
    customerName: Optional[str] = None
    displayId: Optional[str] = None
    subtotal: Optional[float] = None
    discountAmount: Optional[float] = None
    taxRate: Optional[float] = None
    taxAmount: Optional[float] = None
    paymentMethod: Optional[str] = None
    customResponses: Optional[dict] = None  # owner-added custom flow questions → answers, keyed by stepKey


class OrderStatusUpdate(BaseModel):
    paymentStatus: str
    additionalNotes: Optional[str] = None


class OrderListResponse(BaseModel):
    orders: list[OrderOut]
    totalOrders: int
    currentPage: int
    totalPages: int


class OrderStats(BaseModel):
    totalOrders: int
    pending: int
    accepted: int
    preparing: int
    ready: int
    completed: int
    rejected: int
    totalRevenue: float