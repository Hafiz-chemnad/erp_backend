from pydantic import BaseModel
from typing import Optional


class FaqEntry(BaseModel):
    question: str
    answer: str


class PromptConfigIn(BaseModel):
    """What the owner fills in on the Settings setup screen. Never a raw
    prompt — this gets assembled into one server-side (see service.py)."""
    tone: str = "friendly"                 # e.g. friendly | formal | casual | playful
    faqs: list[FaqEntry] = []
    neverDoList: list[str] = []            # e.g. ["Never promise a delivery time", "Never discuss other restaurants"]
    extraInstructions: str = ""            # owner's free-text "anything else?" box


class PromptConfigOut(PromptConfigIn):
    pass


class AiAgentStatusOut(BaseModel):
    enabled: bool
    businessId: Optional[str] = None
    promptConfigured: bool = False


class PlaceOrderItemIn(BaseModel):
    """Only retailerId and qty are trusted from the AI/tool call — price and
    name are always looked up server-side, same anti-tamper pattern as
    Billing's POSOrderItemIn."""
    retailerId: str
    qty: int = 1


class PlaceOrderIn(BaseModel):
    """Body the agent-backend 'place_order' Tool sends to erp_backend.
    This is intentionally a thin, AI-friendly shape — not the POS billing
    shape, since AI-placed orders are always WhatsApp customer self-orders,
    never staff-entered counter/table orders."""
    items: list[PlaceOrderItemIn]
    customerNumber: str
    orderType: str = "DELIVERY"            # DELIVERY | TAKEAWAY
    # Set only once the customer has shared their WhatsApp location pin —
    # the AI is instructed to collect this BEFORE calling place_order for a
    # DELIVERY order, so a normal order already has its address attached at
    # creation (matches the scripted bot's own flow). Left unset for TAKEAWAY.
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    deliveryAddress: Optional[str] = None
    notes: Optional[str] = None


class PlaceOrderOut(BaseModel):
    orderId: str
    totalAmount: float
    status: str
    locationPinNeeded: bool = False


class ChatTurnIn(BaseModel):
    transcript: str
    sessionState: Optional[dict] = None


class ChatTurnOut(BaseModel):
    response: Optional[str] = None
    sessionState: dict = {}
    toolCalled: Optional[dict] = None
