import uuid
from pydantic import BaseModel, Field
from typing import Optional, Any


class FlowStep(BaseModel):
    stepKey: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])  # stable id, used to key customResponses
    stepType: str          # welcome | order_type | category | items | order_summary | location | payment_mode | status | custom_question
    message: str
    replyType: str         # button | location | list | internal | link | text
    options: list[str] = []
    category: str = "functional"  # "functional" (order-logic, protected) | "custom" (owner-added, unlimited, deletable)
    required: bool = True         # only meaningful for custom_question steps — can the customer skip it?


class Flow(BaseModel):
    flowName: str
    steps: list[FlowStep]


# The flow every restaurant runs today, hardcoded here as the ultimate
# fallback. Restaurants who've never opened the Flow Builder still get
# exactly this — get_flow() used to raise if nothing was configured,
# which meant a brand-new restaurant's bot would break outright.
DEFAULT_FLOW_STEPS: list[dict[str, Any]] = [
    {"stepType": "welcome", "message": "Welcome to {{restaurantName}}! 👋 Ready to order?", "replyType": "button", "options": ["Start Order", "Exit"], "category": "functional"},
    {"stepType": "order_type", "message": "Would you like delivery or takeaway?", "replyType": "button", "options": ["Delivery", "Takeaway"], "category": "functional"},
    {"stepType": "category", "message": "Great! What would you like to order today?", "replyType": "list", "category": "functional"},
    {"stepType": "items", "message": "Pick an item from the menu:", "replyType": "list", "category": "functional"},
    {"stepType": "order_summary", "message": "Here's your order so far. Add more items or continue?", "replyType": "button", "options": ["Continue", "Add More", "Cancel"], "category": "functional"},
    {"stepType": "location", "message": "Please share your delivery location 📍", "replyType": "location", "category": "functional"},
    {"stepType": "payment_mode", "message": "", "replyType": "internal", "category": "functional"},
    {"stepType": "status", "message": "✅ Order confirmed!", "replyType": "text", "category": "functional"},
]


def get_default_flow(flow_name: str = "default_flow") -> Flow:
    return Flow(flowName=flow_name, steps=[FlowStep(**s) for s in DEFAULT_FLOW_STEPS])


def get_flow(restaurant: dict, flow_name: str = "default_flow") -> Flow:
    flows = restaurant.get("flows", [])
    for f in flows:
        if f.get("flowName") == flow_name:
            return Flow(**f)
    # No custom flow configured for this restaurant/name yet — fall back to
    # the default rather than breaking the bot for anyone who hasn't
    # opened the Flow Builder.
    return get_default_flow(flow_name)



# ── Step-order rules ────────────────────────────────────────────────────
# Owners may reorder steps (this replaces the old LOCATION_FIRST /
# LOCATION_LAST presets), but a few dependencies are real:
#   welcome       -> must open the conversation
#   category      -> must come before items (items lists the chosen category)
#   items         -> must come before the cart summary
#   status        -> must close the conversation (it is the confirmation)
# Everything else (order type, location, payment, custom questions) is free
# to move — that is what makes "location first", "location last", or
# "ask about spice level before the menu" possible without presets.
def validate_flow_order(steps: list) -> list[str]:
    types = [s.stepType for s in steps]
    first: dict[str, int] = {}
    for i, t in enumerate(types):
        first.setdefault(t, i)
    errors: list[str] = []
    if "welcome" in first and first["welcome"] != 0:
        errors.append("Welcome must stay the first step.")
    if "status" in first and first["status"] != len(types) - 1:
        errors.append("Confirmation must stay the last step.")
    if "category" in first and "items" in first and first["category"] > first["items"]:
        errors.append("Category Selection must come before Item Selection.")
    if "items" in first and "order_summary" in first and first["items"] > first["order_summary"]:
        errors.append("Item Selection must come before the Cart Summary.")
    if "category" in first and "order_summary" in first and first["category"] > first["order_summary"]:
        errors.append("Category Selection must come before the Cart Summary.")
    return errors
