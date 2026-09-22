from pydantic import BaseModel
from typing import Optional


class POSOrderItemIn(BaseModel):
    """A single line the cashier added on the Billing screen.
    Only `retailerId`, `qty` and `note` are trusted from the client —
    `name` and `price` are looked up server-side from menu_items so a
    tampered/stale client payload can never under-charge a bill."""
    retailerId: str
    qty: int = 1
    note: Optional[str] = None


class POSOrderIn(BaseModel):
    """POST .../pos/send-to-kitchen payload. No `items[].price` here on
    purpose — see POSOrderItemIn docstring. No paymentMethod here either —
    payment is only ever captured at settle-payment time."""
    orderMode: str  # dine_in | takeaway_counter | phone_pickup | phone_delivery
    items: list[POSOrderItemIn]
    tableNumber: Optional[str] = None
    existingOrderId: Optional[str] = None  # to add more items to an open takeaway_counter ticket
    customerName: Optional[str] = None
    customerNumber: Optional[str] = None
    discountPercent: float = 0.0
    discountFlat: float = 0.0
    billedBy: Optional[str] = None
    additionalNotes: Optional[str] = None


class EditItemsIn(BaseModel):
    """Full replacement item list for an already-sent order. Omit an item
    that was there before to remove it; qty=0 also removes it."""
    items: list[POSOrderItemIn]
    discountPercent: float = 0.0
    discountFlat: float = 0.0


class SettlePaymentIn(BaseModel):
    orderId: str
    paymentMethod: str  # cash | upi | card | split


class BillLineOut(BaseModel):
    retailerId: str
    name: str
    price: float
    qty: int
    note: Optional[str] = None
    lineTotal: float


class POSOrderOut(BaseModel):
    orderId: str
    displayId: str
    source: str = "pos"
    orderMode: str
    tableNumber: Optional[str] = None
    customerName: Optional[str] = None
    customerNumber: Optional[str] = None
    items: list[BillLineOut]
    subtotal: float
    discountAmount: float
    taxRate: float
    taxAmount: float
    totalAmount: float
    paymentStatus: str
    paymentMethod: Optional[str] = None
    billedBy: Optional[str] = None
    additionalNotes: Optional[str] = None
    restaurantId: str
    restaurantName: str
    createdAt: str


class OpenTableOut(BaseModel):
    tableNumber: str
    orderId: str
    displayId: str
    totalAmount: float
    itemCount: int
    createdAt: str


class OpenPhoneOrderOut(BaseModel):
    orderId: str
    displayId: str
    orderMode: str
    customerName: Optional[str] = None
    customerNumber: Optional[str] = None
    paymentStatus: str
    totalAmount: float
    itemCount: int
    createdAt: str


class OpenCounterTicketOut(BaseModel):
    orderId: str
    displayId: str
    customerName: Optional[str] = None
    totalAmount: float
    itemCount: int
    createdAt: str


class OpenPhoneOrderOut(BaseModel):
    orderId: str
    displayId: str
    orderMode: str
    paymentStatus: str
    customerName: Optional[str] = None
    customerNumber: Optional[str] = None
    totalAmount: float
    itemCount: int
    hasLocation: bool = False
    createdAt: str


class CloseTableIn(BaseModel):
    paymentMethod: str


class MergeTablesIn(BaseModel):
    sourceTable: str
    targetTable: str


class MoveTableIn(BaseModel):
    newTable: str
