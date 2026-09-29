"""
The orchestrator. Called once per inbound WhatsApp message from webhooks/router.py.

Steps are driven entirely by the restaurant's flow (see flow_schema.py), so the
owner can reorder them in the Flow Editor. Nothing here assumes a fixed order:

  * the order is created when the conversation reaches the confirmation step
    (or the end of the flow) — NOT when a particular step finishes — so
    "location first", "location last" and custom questions in the middle all
    produce a complete order;
  * steps whose answer is already known (order type, location, a custom
    question) are skipped, so "Add More" loops don't re-ask them;
  * the location step is skipped for takeaway orders.
"""

import logging
import random
from app.bot_engine import session as session_store, step_handlers
from app.bot_engine.flow_schema import get_flow
from app.bot_engine.meta_sender import send_text, send_buttons, request_location, send_list
from app.orders import service as order_service
from app.db import get_database

logger = logging.getLogger(__name__)


def _generate_order_id() -> str:
    return f"ORD-{random.randint(100000, 999999)}-{random.randint(100, 999)}"


def _category_index(flow) -> int:
    for i, s in enumerate(flow.steps):
        if s.stepType == "category":
            return i
    return 0


def _cart_lines(cart: list) -> str:
    return "\n".join(f"• {i['name']} x{i['qty']} = ₹{i['price'] * i['qty']}" for i in cart)


def _should_skip(step, session) -> bool:
    """True for steps the customer should not be asked (again)."""
    data = session["data"]
    if step.replyType == "internal":
        return True
    if step.stepType == "order_type" and data.get("orderType"):
        return True
    if step.stepType == "location" and (data.get("orderType") == "TAKEAWAY" or data.get("location")):
        return True
    if step.stepType == "custom_question" and step.stepKey in data.get("customResponses", {}):
        return True
    return False


def _next_index(flow, session, start: int) -> int:
    """First index >= start that should actually be shown to the customer.
    Silent bookkeeping steps (payment_mode) are executed on the way past."""
    i = start
    while i < len(flow.steps) and _should_skip(flow.steps[i], session):
        if flow.steps[i].stepType == "payment_mode":
            step_handlers.handle_payment_mode({}, session)
        i += 1
    return i


async def _send_step_message(step, restaurant, to, wa_token, session):
    phone_number_id = restaurant["phoneNumberId"]
    text = step.message.replace("{{restaurantName}}", restaurant.get("name", ""))
    db = get_database()
    restaurant_id = str(restaurant["_id"])

    if step.stepType == "category":
        categories = await db.menu_items.distinct(
            "category", {"restaurant_id": restaurant_id, "is_available": True}
        )
        if not categories:
            await send_text(phone_number_id, to, "Sorry, no menu categories are available right now.", wa_token)
            return
        items = [{"id": c, "title": c, "description": ""} for c in categories]
        await send_list(phone_number_id, to, restaurant.get("name", "Menu"), text, items, wa_token)

    elif step.stepType == "items":
        category = session["data"].get("selectedCategory")
        cursor = db.menu_items.find({
            "restaurant_id": restaurant_id, "category": category, "is_available": True,
        })
        docs = [d async for d in cursor]
        if not docs:
            await send_text(phone_number_id, to, "No items found in that category.", wa_token)
            return
        items = [
            {"id": d["retailer_id"], "title": d["name"], "description": f"₹{d['price']}"}
            for d in docs
        ]
        await send_list(phone_number_id, to, category, text, items, wa_token)

    elif step.stepType == "order_summary":
        cart = session["data"].get("cart", [])
        body = text
        if cart:
            total = sum(i["price"] * i["qty"] for i in cart)
            body = f"{text}\n\n🛒 Your cart:\n{_cart_lines(cart)}\n\n💰 Total: ₹{total}"
        options = step.options or ["Continue", "Add More", "Cancel"]
        await send_buttons(phone_number_id, to, body[:1024], options, wa_token)

    elif step.replyType == "button" and step.options:
        await send_buttons(phone_number_id, to, text, step.options, wa_token)
    elif step.replyType == "list" and step.options:
        items = [{"id": o, "title": o, "description": ""} for o in step.options]
        await send_list(phone_number_id, to, restaurant.get("name", "Menu"), text, items, wa_token)
    elif step.replyType == "location":
        await request_location(phone_number_id, to, text, wa_token)
    else:
        await send_text(phone_number_id, to, text, wa_token)


async def _create_order(restaurant: dict, session: dict, customer_number: str):
    """Persists the order from whatever the session collected. Idempotent per
    session (orderCompleted) and a no-op for an empty cart."""
    data = session["data"]
    cart = data.get("cart", [])
    if data.get("orderCompleted") or not cart:
        return None
    order_doc = {
        "orderId": _generate_order_id(),
        "customerNumber": customer_number,
        "items": cart,
        "totalAmount": sum(i["price"] * i["qty"] for i in cart),
        "paymentStatus": "pending",
        "orderType": data.get("orderType", "DELIVERY"),
        "restaurantId": restaurant["_id"],
        "restaurantName": restaurant.get("name", ""),
        "location": data.get("location"),
        "customResponses": data.get("customResponses"),
    }
    created = await order_service.create_order(order_doc)
    data["orderCompleted"] = True
    data["lastCompletedOrderId"] = created["orderId"]
    data["lastOrderTotal"] = order_doc["totalAmount"]
    return created


async def handle_message(restaurant: dict, incoming: dict, customer_number: str):
    phone_number_id = restaurant["phoneNumberId"]
    wa_token = restaurant["waToken"]
    restaurant_id = str(restaurant["_id"])
    db = get_database()

    session = await session_store.load(phone_number_id, customer_number)
    flow = get_flow(restaurant, session["flowName"])
    if not flow.steps:
        return

    # First contact (or the owner shortened the flow under a running session):
    # open the conversation with the first step instead of consuming the
    # customer's "hi" as an answer. Without this the welcome message — and any
    # edits made to it in the Flow Editor — was never actually sent.
    if session.get("fresh") or session["stepIndex"] >= len(flow.steps):
        session["fresh"] = False
        session["stepIndex"] = _next_index(flow, session, 0)
        if session["stepIndex"] >= len(flow.steps):
            return
        await session_store.save(phone_number_id, customer_number, session)
        await _send_step_message(flow.steps[session["stepIndex"]], restaurant, customer_number, wa_token, session)
        return

    step_index = session["stepIndex"]
    step = flow.steps[step_index]

    advanced = False

    if step.stepType == "welcome":
        advanced = step_handlers.handle_welcome(incoming, session)
        if not advanced:  # user pressed Exit
            await session_store.clear(phone_number_id, customer_number)
            await send_text(phone_number_id, customer_number, "Okay, come back anytime! 👋", wa_token)
            return

    elif step.stepType == "order_type":
        advanced = step_handlers.handle_order_type(incoming, session)

    elif step.stepType == "category":
        advanced = step_handlers.handle_category(incoming, session)

    elif step.stepType == "items":
        if incoming.get("type") == "interactive":
            reply = incoming["interactive"].get("list_reply", {})
            retailer_id = reply.get("id")
            if retailer_id:
                doc = await db.menu_items.find_one({"restaurant_id": restaurant_id, "retailer_id": retailer_id})
                if doc:
                    cart = session["data"].setdefault("cart", [])
                    existing = next((c for c in cart if c.get("retailer_id") == retailer_id), None)
                    if existing:
                        existing["qty"] += 1
                    else:
                        cart.append({"name": doc["name"], "price": doc["price"], "qty": 1, "retailer_id": retailer_id})
                    advanced = True

    elif step.stepType == "order_summary":
        decision = step_handlers.handle_order_summary(incoming, session, step.options)
        if decision == "cancel":
            await session_store.clear(phone_number_id, customer_number)
            await send_text(phone_number_id, customer_number, "Order cancelled. Send any message to start again.", wa_token)
            return
        if decision == "add_more":
            session["stepIndex"] = _category_index(flow)
            await session_store.save(phone_number_id, customer_number, session)
            await _send_step_message(flow.steps[session["stepIndex"]], restaurant, customer_number, wa_token, session)
            return
        advanced = decision == "continue"

    elif step.stepType == "location":
        advanced = step_handlers.handle_location(incoming, session)

    elif step.stepType == "payment_mode":
        advanced = step_handlers.handle_payment_mode(incoming, session)

    elif step.stepType == "custom_question":
        advanced = step_handlers.handle_custom(
            incoming, session, step.stepKey, step.required,
            question=step.message.replace("{{restaurantName}}", restaurant.get("name", "")),
        )

    elif step.stepType == "status":
        advanced = False  # terminal

    if not advanced:
        await _send_step_message(step, restaurant, customer_number, wa_token, session)
        await session_store.save(phone_number_id, customer_number, session)
        return

    next_index = _next_index(flow, session, step_index + 1)

    # End of the conversation: either the confirmation step is next, or the
    # owner's flow simply ends. Create the order NOW — every answer the
    # customer gave (location, custom questions, …) is in the session no
    # matter which order the owner arranged the steps in.
    reached_end = next_index >= len(flow.steps)
    reached_status = (not reached_end) and flow.steps[next_index].stepType == "status"
    if reached_end or reached_status:
        await _create_order(restaurant, session, customer_number)

    if reached_end:
        await session_store.clear(phone_number_id, customer_number)
        return

    if reached_status:
        next_step = flow.steps[next_index]
        cart = session["data"].get("cart", [])
        text = (
            f"{next_step.message}\n\n"
            f"📦 Order ID: {session['data'].get('lastCompletedOrderId', '')}\n\n"
            f"🛒 Items:\n{_cart_lines(cart)}\n\n"
            f"💰 Total Amount: ₹{session['data'].get('lastOrderTotal', 0)}\n\n"
            f"🙏 Thank you for ordering with {restaurant.get('name', '')}."
        )
        await send_text(phone_number_id, customer_number, text, wa_token)
        await session_store.clear(phone_number_id, customer_number)
        return

    session["stepIndex"] = next_index
    await session_store.save(phone_number_id, customer_number, session)
    await _send_step_message(flow.steps[next_index], restaurant, customer_number, wa_token, session)
