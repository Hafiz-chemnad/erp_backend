"""
One function per stepType. Each handler:
  - reads the incoming message
  - updates session["data"]
  - returns True if the step is satisfied (advance to next step)
    or False if the bot should re-prompt (invalid input)
"""


def handle_welcome(incoming: dict, session: dict) -> bool:
    if incoming.get("type") == "interactive":
        reply = incoming["interactive"].get("button_reply", {})
        if reply.get("title") == "Exit":
            return False  # engine treats this as a special reset, handled separately
    return True  # any other message moves past welcome


def handle_order_type(incoming: dict, session: dict) -> bool:
    if incoming.get("type") == "interactive":
        reply = incoming["interactive"].get("button_reply", {})
        title = reply.get("title", "")
        if title in ("Delivery", "Takeaway"):
            session["data"]["orderType"] = "DELIVERY" if title == "Delivery" else "TAKEAWAY"
            return True
    return False


def handle_category(incoming: dict, session: dict) -> bool:
    if incoming.get("type") == "interactive":
        reply = incoming["interactive"].get("list_reply", {})
        category = reply.get("title")
        if category:
            session["data"]["selectedCategory"] = category
            return True
    return False


def handle_location(incoming: dict, session: dict) -> bool:
    if incoming.get("type") == "location":
        session["data"]["location"] = {
            "lat": incoming["location"]["latitude"],
            "lng": incoming["location"]["longitude"],
        }
        return True
    if incoming.get("type") == "text":
        text = incoming.get("text", {}).get("body", "").strip().lower()
        if text.startswith("location:"):
            try:
                lat_str, lng_str = text.replace("location:", "").strip().split(",")
                session["data"]["location"] = {"lat": float(lat_str), "lng": float(lng_str)}
                return True
            except ValueError:
                return False
    return False


def handle_order_summary(incoming: dict, session: dict) -> str:
    """Returns 'continue' | 'cancel' | 'add_more' | None (invalid)."""
    if incoming.get("type") == "interactive":
        reply = incoming["interactive"].get("button_reply", {})
        title = reply.get("title", "")
        if title == "Confirm Order":
            return "continue"
        if title == "Cancel Order":
            return "cancel"
        if title == "Add More Items":
            return "add_more"
    return None


def handle_payment_mode(incoming: dict, session: dict) -> bool:
    session["data"]["paymentMode"] = "COD"  # COD-only for now
    return True


def handle_custom(incoming: dict, session: dict, step_key: str, required: bool = True) -> bool:
    """Generic handler for owner-added Custom Questions (bot_flow builder).
    Accepts any reply type — text, a button title, or a list selection —
    and stores it verbatim under customResponses, keyed by the step's
    stable stepKey (not its message text, since that can be edited later
    without orphaning already-collected answers). Always advances once a
    reply is present; a `required` step still waits for *some* reply, an
    optional one advances even on an empty/skip-style message.
    """
    answer = None
    if incoming.get("type") == "text":
        answer = incoming.get("text", {}).get("body", "").strip()
    elif incoming.get("type") == "interactive":
        interactive = incoming["interactive"]
        if "button_reply" in interactive:
            answer = interactive["button_reply"].get("title")
        elif "list_reply" in interactive:
            answer = interactive["list_reply"].get("title")

    if answer:
        session["data"].setdefault("customResponses", {})[step_key] = answer
        return True

    # No usable reply. Optional questions still let the customer through
    # (e.g. they sent something we can't parse, like an image) — required
    # ones wait for a real answer.
    return not required