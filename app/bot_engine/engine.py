"""
The orchestrator. Called once per inbound WhatsApp message from webhooks/router.py.

Flow: welcome -> order_type -> category -> items -> order_summary ->
      (add_more loops back to category) -> location -> payment_mode (skip) -> status
"""

import random
from app.bot_engine import session as session_store, step_handlers
from app.bot_engine.flow_schema import get_flow
from app.bot_engine.meta_sender import send_text, send_buttons, request_location, send_list
from app.orders import service as order_service
from app.db import get_database


def _generate_order_id() -> str:
    return f"ORD-{random.randint(100000, 999999)}-{random.randint(100, 999)}"


def _category_index(flow) -> int:
    for i, s in enumerate(flow.steps):
        if s.stepType == "category":
            return i
    return 0


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

    elif step.replyType == "button" and step.options:
        await send_buttons(phone_number_id, to, text, step.options, wa_token)
    elif step.replyType == "location":
        await request_location(phone_number_id, to, text, wa_token)
    else:
        await send_text(phone_number_id, to, text, wa_token)


async def handle_message(restaurant: dict, incoming: dict, customer_number: str):
    phone_number_id = restaurant["phoneNumberId"]
    wa_token = restaurant["waToken"]
    restaurant_id = str(restaurant["_id"])
    db = get_database()

    session = await session_store.load(phone_number_id, customer_number)
    flow = get_flow(restaurant, session["flowName"])
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
                    cart.append({"name": doc["name"], "price": doc["price"], "qty": 1, "retailer_id": retailer_id})
                    advanced = True

    elif step.stepType == "order_summary":
        decision = step_handlers.handle_order_summary(incoming, session)
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
        advanced = step_handlers.handle_custom(incoming, session, step.stepKey, step.required)

    elif step.stepType == "status":
        advanced = False  # terminal

    if not advanced:
        await _send_step_message(step, restaurant, customer_number, wa_token, session)
        await session_store.save(phone_number_id, customer_number, session)
        return

    next_index = step_index + 1

    # Order gets created right after location is confirmed (last real input step)
    if step.stepType == "location":
        cart = session["data"].get("cart", [])
        order_doc = {
            "orderId": _generate_order_id(),
            "customerNumber": customer_number,
            "items": cart,
            "totalAmount": sum(i["price"] * i["qty"] for i in cart),
            "paymentStatus": "pending",
            "orderType": session["data"].get("orderType", "DELIVERY"),
            "restaurantId": restaurant["_id"],
            "restaurantName": restaurant.get("name", ""),
            "location": session["data"].get("location"),
            "customResponses": session["data"].get("customResponses"),
        }
        created = await order_service.create_order(order_doc)
        session["data"]["orderCompleted"] = True
        session["data"]["lastCompletedOrderId"] = created["orderId"]
        session["data"]["lastOrderTotal"] = order_doc["totalAmount"]

    if next_index >= len(flow.steps):
        await session_store.clear(phone_number_id, customer_number)
        return

    session["stepIndex"] = next_index
    await session_store.save(phone_number_id, customer_number, session)



    # Auto-advance through any silent steps (payment_mode, or anything with
    # replyType "internal") without sending a message or waiting for input —
    # these are engine-only bookkeeping steps, not real conversation turns.
    while next_index < len(flow.steps) and flow.steps[next_index].replyType == "internal":
        auto_step = flow.steps[next_index]
        if auto_step.stepType == "payment_mode":
            step_handlers.handle_payment_mode(incoming, session)
        next_index += 1

    if next_index >= len(flow.steps):
        await session_store.clear(phone_number_id, customer_number)
        return

    session["stepIndex"] = next_index
    await session_store.save(phone_number_id, customer_number, session)

    next_step = flow.steps[next_index]
    if next_step.stepType == "status":
        cart = session["data"].get("cart", [])
        items_list = "\n".join(f"• {i['name']} x{i['qty']} = ₹{i['price'] * i['qty']}" for i in cart)
        text = (
            f"{next_step.message}\n\n"
            f"📦 Order ID: {session['data'].get('lastCompletedOrderId','')}\n\n"
            f"🛒 Items:\n{items_list}\n\n"
            f"💰 Total Amount: ₹{session['data'].get('lastOrderTotal', 0)}\n\n"
            f"🙏 Thank you for ordering with {restaurant.get('name','')}."
        )
        await send_text(phone_number_id, customer_number, text, wa_token)
        await session_store.clear(phone_number_id, customer_number)
        return

    await _send_step_message(next_step, restaurant, customer_number, wa_token, session)