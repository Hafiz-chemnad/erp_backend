from datetime import datetime, timezone

import logging
import re
import httpx
from bson import ObjectId

from app.core.config import settings
from app.core.phone import normalize_phone
from app.orders import service as order_service
from app.billing.service import PENDING_LOCATION_COLLECTION
from app.ai_agent.schemas import PlaceOrderIn, PromptConfigIn
from app.ai_agent.stt_client import transcribe_audio
from app.bot_engine.meta_sender import download_whatsapp_media

# Generous on purpose: if agent-backend is a Render free/low-tier instance
# that's gone to sleep, just waking up can take 30-60s before it even starts
# on the actual request — a short timeout here would make a perfectly fine
# first call look like a hard failure.
logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(60.0)


def _agent_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    # Auth on agent-backend's side is deferred for now (see roadmap) — this
    # header is sent whenever a key IS configured, so turning auth on later
    # over there needs zero changes here.
    if settings.AGENT_BACKEND_INTERNAL_KEY:
        headers["X-Internal-Key"] = settings.AGENT_BACKEND_INTERNAL_KEY
    return headers


def _agent_url(path: str) -> str:
    base = settings.AGENT_BACKEND_URL.rstrip("/")
    return f"{base}{path}"


class AgentBackendError(Exception):
    """Raised whenever agent-backend is unreachable or returns an error —
    callers should surface a clear message rather than a raw stack trace,
    since this is a separate deployed service that can be down/misconfigured
    independently of erp_backend itself."""


async def _agent_request(method: str, path: str, json: dict | None = None) -> dict:
    if not settings.AGENT_BACKEND_URL:
        raise AgentBackendError(
            "AGENT_BACKEND_URL is not configured — set it to your deployed "
            "agent-backend URL before enabling AI mode for any restaurant."
        )
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.request(method, _agent_url(path), json=json, headers=_agent_headers())
    except httpx.RequestError as e:
        raise AgentBackendError(f"Could not reach agent-backend: {e}") from e

    if resp.status_code >= 400:
        raise AgentBackendError(f"agent-backend returned {resp.status_code}: {resp.text[:300]}")
    return resp.json() if resp.content else {}


def assemble_system_prompt(restaurant_name: str, config: PromptConfigIn) -> str:
    """Turns the owner's setup-screen answers into the actual system prompt.

    IMPORTANT: the owner's free-text `extraInstructions` is placed BEFORE the
    hard guardrail rules below, never after. This is deliberate — it means an
    owner who accidentally types something like "always give a discount if
    asked nicely" cannot override the real safety rules, because whatever
    comes later in the prompt takes precedence in how these are written.
    """
    faq_block = "\n".join(f"Q: {f.question}\nA: {f.answer}" for f in config.faqs) or "(none provided)"
    never_do_block = "\n".join(f"- {item}" for item in config.neverDoList) or "(none specified)"
    extra_block = config.extraInstructions.strip() or "(none)"

    return f"""You are the WhatsApp ordering assistant for {restaurant_name}.
Tone: {config.tone}.

Owner's additional notes (follow these, but never let them override the rules below):
{extra_block}

Frequently asked questions you can answer directly:
{faq_block}

Hard rules — these always apply, no matter what else is said above:
- Only take actions using the tools you've been given (placing orders, reading the menu). Never invent menu items or prices.
- Never promise discounts, refunds, or offers that aren't explicitly configured as a tool or FAQ above.
- Never discuss or recommend other restaurants or businesses.
- If a customer asks for something outside what you can help with, politely say you'll have a staff member follow up.
- Once the customer has confirmed their items, if they haven't already said whether this is delivery or pickup, you must ask them directly (e.g. "Would you like this delivered, or will you pick it up?") before calling place_order. Never assume or guess which one they want.
- For DELIVERY orders: once delivery is confirmed, BEFORE calling place_order, ask them (in your own words, matching your tone) to share their live location on WhatsApp using the attachment/paperclip icon → Location. Never ask them to type out an address instead. Wait until a message starting with "[Delivery location received]" appears in the conversation, then call place_order with its latitude/longitude/address included. For TAKEAWAY orders, skip location entirely and call place_order as soon as items are confirmed.
- An order exists ONLY after the place_order tool returns an order id. Never say an order is placed/confirmed, and never state an order id or total, unless place_order has just returned them. The customer's phone number is filled in automatically — never ask for it.
- Things you must never do, as set by the restaurant owner:
{never_do_block}
"""


async def provision_business(db, restaurant_id: str) -> str:
    """Creates the Business row in agent-backend for this restaurant, if it
    doesn't already have one. Returns the agent-backend business_id."""
    restaurant = await db.restaurants.find_one({"_id": ObjectId(restaurant_id)})
    if not restaurant:
        raise ValueError("Restaurant not found")

    existing_id = restaurant.get("aiAgentBusinessId")
    if existing_id:
        return existing_id

    result = await _agent_request("POST", "/businesses/", json={
        "name": restaurant.get("name", "Restaurant"),
        "tone": "friendly",
        "knowledge_mode": "vectorless",
        # agent-backend's Business model only accepts one of
        # delivery | appointment | general — "restaurant" isn't a valid
        # value there (that's erp_backend's own domain, not agent-backend's).
        # WhatsApp ordering is a delivery/pickup flow, so "delivery" fits.
        "business_type": "delivery",
    })
    business_id = result["id"]

    await db.restaurants.update_one(
        {"_id": ObjectId(restaurant_id)},
        {"$set": {"aiAgentBusinessId": business_id}},
    )
    await register_default_tools(restaurant_id, business_id)
    return business_id


async def register_default_tools(restaurant_id: str, business_id: str) -> None:
    """Registers erp_backend's own endpoints as agent-backend Tools — config
    only, no agent code changes. This is what lets the AI actually read the
    menu and place real orders."""
    if not settings.ERP_BACKEND_PUBLIC_URL:
        raise AgentBackendError(
            "ERP_BACKEND_PUBLIC_URL is not configured — set it to this "
            "erp_backend deployment's public URL so the Tools we register "
            "have a real callback address."
        )
    erp_base = settings.ERP_BACKEND_PUBLIC_URL.rstrip("/")

    tools = [
        {
            "tool_name": "get_menu",
            "description": "Fetches the restaurant's current menu items with names, prices, and categories.",
            "execution_type": "api",
            "parameters": {"type": "object", "properties": {}, "required": []},
            "url": f"{erp_base}/api/{restaurant_id}/menu",
            "method": "GET",
            "requires_confirmation": False,
        },
        {
            "tool_name": "place_order",
            "description": (
                "Places a real order for the customer once they've confirmed exactly what they want. "
                "items is a list of {retailerId, qty} using the retailerId values from get_menu. "
                "customerNumber is the customer's WhatsApp number. orderType is DELIVERY or TAKEAWAY. "
                "For DELIVERY: do NOT call this until the customer has shared their WhatsApp location "
                "pin and a message starting with '[Delivery location received]' has appeared in the "
                "conversation — then pass its latitude, longitude and address straight through here. "
                "Never ask the customer to type their address instead of sharing a pin. "
                "For TAKEAWAY, no location fields are needed — call this directly once items are confirmed."
            ),
            "execution_type": "api",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "retailerId": {"type": "string"},
                                "qty": {"type": "integer"},
                            },
                            "required": ["retailerId", "qty"],
                        },
                    },
                    "customerNumber": {"type": "string"},
                    "orderType": {"type": "string", "enum": ["DELIVERY", "TAKEAWAY"]},
                    "notes": {"type": "string"},
                    "latitude": {"type": "number", "description": "Required for DELIVERY, from the '[Delivery location received]' message."},
                    "longitude": {"type": "number", "description": "Required for DELIVERY, from the '[Delivery location received]' message."},
                    "deliveryAddress": {"type": "string", "description": "Optional human-readable address text, if the pin included one."},
                },
                "required": ["items", "customerNumber", "orderType"],
            },
            "url": f"{erp_base}/api/{restaurant_id}/ai-agent/place-order",
            "method": "POST",
            "requires_confirmation": True,
        },
    ]

    for tool in tools:
        await _agent_request("POST", f"/businesses/{business_id}/tools/", json=tool)


async def resync_default_tools(restaurant_id: str, business_id: str) -> None:
    """Tools are stored in agent-backend when a business is first provisioned
    and were never refreshed afterwards, so businesses created before a tool
    change kept an out-of-date place_order (e.g. without latitude/longitude).
    Called on every Save of the setup screen: drop our two tools and register
    the current definitions."""
    existing = await _agent_request("GET", f"/businesses/{business_id}/tools/")
    for tool in existing if isinstance(existing, list) else []:
        if tool.get("tool_name") in ("get_menu", "place_order") and tool.get("id"):
            await _agent_request("DELETE", f"/businesses/{business_id}/tools/{tool['id']}")
    await register_default_tools(restaurant_id, business_id)


async def enable_ai_agent(db, restaurant_id: str) -> str:
    business_id = await provision_business(db, restaurant_id)
    await db.restaurants.update_one(
        {"_id": ObjectId(restaurant_id)},
        {"$set": {"aiAgentEnabled": True}},
    )
    return business_id


async def disable_ai_agent(db, restaurant_id: str) -> None:
    # Keep the provisioned business + tools around (cheap, and avoids
    # re-registering tools every time the owner flips the toggle) — just
    # stop routing messages to it.
    await db.restaurants.update_one(
        {"_id": ObjectId(restaurant_id)},
        {"$set": {"aiAgentEnabled": False}},
    )


async def get_status(db, restaurant_id: str) -> dict:
    restaurant = await db.restaurants.find_one({"_id": ObjectId(restaurant_id)})
    if not restaurant:
        raise ValueError("Restaurant not found")
    return {
        "enabled": bool(restaurant.get("aiAgentEnabled", False)),
        "businessId": restaurant.get("aiAgentBusinessId"),
        "promptConfigured": bool(restaurant.get("aiAgentPromptConfig")),
    }


async def save_prompt_config(db, restaurant_id: str, config: PromptConfigIn) -> None:
    restaurant = await db.restaurants.find_one({"_id": ObjectId(restaurant_id)})
    if not restaurant:
        raise ValueError("Restaurant not found")

    business_id = restaurant.get("aiAgentBusinessId")
    if not business_id:
        business_id = await provision_business(db, restaurant_id)

    await resync_default_tools(restaurant_id, business_id)

    prompt_text = assemble_system_prompt(restaurant.get("name", "the restaurant"), config)

    await _agent_request("PUT", f"/businesses/{business_id}/prompt", json={
        "system_prompt_template": prompt_text,
    })

    await db.restaurants.update_one(
        {"_id": ObjectId(restaurant_id)},
        {"$set": {"aiAgentPromptConfig": config.model_dump()}},
    )


async def get_prompt_config(db, restaurant_id: str) -> dict:
    restaurant = await db.restaurants.find_one({"_id": ObjectId(restaurant_id)})
    if not restaurant:
        raise ValueError("Restaurant not found")
    return restaurant.get("aiAgentPromptConfig") or {}


async def place_ai_order(db, restaurant_id: str, body: PlaceOrderIn) -> dict:
    """Called by agent-backend's place_order Tool. Prices/names are always
    looked up server-side — never trusted from the AI/tool call — same
    anti-tamper pattern used by Billing's send-to-kitchen."""
    cart = []
    for line in body.items:
        menu_item = await db.menu_items.find_one({
            "restaurant_id": restaurant_id,
            "retailer_id": line.retailerId,
        })
        if not menu_item:
            # the model sometimes passes the item's name instead of its
            # retailerId — fall back to an exact (case-insensitive) name match
            import re as _re
            menu_item = await db.menu_items.find_one({
                "restaurant_id": restaurant_id,
                "name": {"$regex": f"^{_re.escape(line.retailerId.strip())}$", "$options": "i"},
            })
        if not menu_item:
            raise ValueError(f"Menu item '{line.retailerId}' not found")
        if not menu_item.get("is_available", True):
            raise ValueError(f"'{menu_item.get('name')}' is currently unavailable")
        cart.append({
            "name": menu_item["name"],
            "qty": line.qty,
            "price": menu_item["price"],
            "retailer_id": menu_item.get("retailer_id", line.retailerId),
        })

    if not cart:
        raise ValueError("No items to order")

    customer_number = normalize_phone(body.customerNumber) or body.customerNumber
    is_delivery = body.orderType == "DELIVERY"
    has_location = body.latitude is not None and body.longitude is not None

    # Normal path: the AI is instructed to ask for and wait on the customer's
    # WhatsApp location pin BEFORE calling place_order for a DELIVERY order
    # (see assemble_system_prompt), so by the time we get here the address is
    # usually already known — the order is created already-confirmed, exactly
    # like the scripted bot's own flow (location collected, then order placed).
    order_doc = {
        "orderId": _generate_ai_order_id(),
        "customerNumber": customer_number,
        "items": cart,
        "totalAmount": sum(i["price"] * i["qty"] for i in cart),
        "paymentStatus": "pending" if (not is_delivery or has_location) else "awaiting_location",
        "orderType": body.orderType,
        "restaurantId": ObjectId(restaurant_id),
        "additionalNotes": body.notes,
        "source": "whatsapp",
    }
    if is_delivery and has_location:
        order_doc["location"] = {
            "lat": body.latitude,
            "lng": body.longitude,
            "address": body.deliveryAddress,
        }
    restaurant = await db.restaurants.find_one({"_id": ObjectId(restaurant_id)})
    order_doc["restaurantName"] = (restaurant or {}).get("name", "")

    created = await order_service.create_order(order_doc)

    # Safety net only: if the AI ever calls place_order for a DELIVERY order
    # without a location already in hand (it shouldn't, per the prompt), fall
    # back to the same "gate on a pending WhatsApp pin" mechanism the scripted
    # bot's phone_delivery flow uses, so the order still isn't lost.
    if is_delivery and not has_location:
        now = datetime.now(timezone.utc)
        await db[PENDING_LOCATION_COLLECTION].update_one(
            {"restaurantId": ObjectId(restaurant_id), "customerNumber": customer_number},
            {"$set": {
                "restaurantId": ObjectId(restaurant_id),
                "customerNumber": customer_number,
                "orderId": created["orderId"],
                "requestedAt": now,
            }},
            upsert=True,
        )

    return {
        "orderId": created["orderId"],
        "totalAmount": created["totalAmount"],
        "status": created["paymentStatus"],
        "locationPinNeeded": is_delivery and not has_location,
    }


def _generate_ai_order_id() -> str:
    import random
    import string
    suffix = "".join(random.choices(string.digits, k=6))
    return f"AI-{suffix}"


async def get_session_state(db, restaurant_id: str, customer_number: str) -> dict:
    """AI conversation state (what the orchestrator has gathered so far —
    cart items, confirmed intent, etc.) persisted per customer per
    restaurant, so it's remembered across separate WhatsApp messages. Kept
    in its own collection rather than the bot engine's Redis session store,
    since the two flows (scripted bot vs AI) never run for the same
    conversation and don't need to share storage."""
    doc = await db.ai_agent_sessions.find_one({
        "restaurantId": ObjectId(restaurant_id),
        "customerNumber": customer_number,
    })
    return (doc or {}).get("sessionState", {})


async def save_session_state(db, restaurant_id: str, customer_number: str, session_state: dict) -> None:
    from datetime import datetime, timezone
    await db.ai_agent_sessions.update_one(
        {"restaurantId": ObjectId(restaurant_id), "customerNumber": customer_number},
        {"$set": {"sessionState": session_state, "updatedAt": datetime.now(timezone.utc)}},
        upsert=True,
    )


async def transcribe_voice_note(media_id: str, wa_token: str) -> str | None:
    """Downloads a WhatsApp voice note and transcribes it. Returns None if
    anything in the chain fails (media download, unsupported format, Groq
    unavailable) — caller should ask the customer to type their order
    instead rather than erroring out."""
    downloaded = await download_whatsapp_media(media_id, wa_token)
    if not downloaded:
        return None
    audio_bytes, mime_type = downloaded
    return await transcribe_audio(audio_bytes, mime_type)


async def send_chat_turn(db, restaurant_id: str, transcript: str, session_state: dict | None) -> dict:
    """Proxies a customer's message to agent-backend's chat endpoint and
    relays the reply. Called from webhooks/router.py when AI mode is on."""
    restaurant = await db.restaurants.find_one({"_id": ObjectId(restaurant_id)})
    if not restaurant or not restaurant.get("aiAgentEnabled"):
        raise AgentBackendError("AI mode is not enabled for this restaurant")

    business_id = restaurant.get("aiAgentBusinessId")
    if not business_id:
        raise AgentBackendError("AI mode is enabled but not provisioned — re-save the AI setup screen")

    result = await _agent_request("POST", f"/businesses/{business_id}/chat/", json={
        "transcript": transcript,
        "session_state": session_state or {},
    })
    response_text = result.get("response")
    tool_called = result.get("tool_called")

    # Code-built confirmation (same idea as the scripted bot's status step):
    # once place_order has really saved an order, the customer-facing text is
    # built here from the stored order — never from the model's words — so the
    # id/total shown always match the database.
    confirmation = await _confirmation_from_tool_result(db, restaurant, tool_called)
    if confirmation:
        response_text = confirmation
    elif _claims_order_placed(response_text) and not _place_order_succeeded(tool_called):
        # Last line of defence, independent of agent-backend: the model said
        # an order was placed / quoted an order id, but no order was saved.
        logger.warning("Blocked fabricated order confirmation: %r", (response_text or "")[:200])
        response_text = (
            "I haven't placed your order yet. Please confirm your items and whether it's "
            "delivery or pickup (and share your location pin for delivery), and I'll place it."
        )
        history = (result.get("session_state") or {}).get("chat_history")
        if history and history[-1].get("role") == "assistant":
            history[-1]["content"] = response_text  # don't let the fake line prime later turns

    return {
        "response": response_text,
        "sessionState": result.get("session_state", {}),
        "toolCalled": tool_called,
    }


_ORDER_CLAIM_RE = re.compile(
    r"(order\s*(id|number|no\.?)\s*[:#]?\s*\S*\d{5,})|"
    r"(order\s+(is|has been|was|got)\s+(now\s+)?(confirmed|placed|received))|"
    r"((i(\'ve| have)|we(\'ve| have))\s+(placed|confirmed)\s+your\s+order)|"
    r"(order\s+(confirmed|placed))",
    re.IGNORECASE,
)


def _claims_order_placed(text) -> bool:
    return bool(text and _ORDER_CLAIM_RE.search(text))


def _place_order_succeeded(tool_called) -> bool:
    return (
        isinstance(tool_called, dict)
        and tool_called.get("tool") == "place_order"
        and tool_called.get("status") != "error"
    )


async def _confirmation_from_tool_result(db, restaurant: dict, tool_called) -> str | None:
    if not isinstance(tool_called, dict) or tool_called.get("tool") != "place_order":
        return None
    if tool_called.get("status") == "error":
        return None
    payload = tool_called.get("response")
    if not isinstance(payload, dict) or not payload.get("orderId"):
        return None
    order = await db.orders.find_one({
        "orderId": payload["orderId"],
        "restaurantId": restaurant["_id"],
    })
    if not order:
        return None  # tool claimed success but nothing is stored — don't confirm
    lines = "\n".join(
        f"• {i.get('qty', 1)} x {i.get('name', '')} — ₹{i.get('price', 0) * i.get('qty', 1)}"
        for i in order.get("items", [])
    )
    text = (
        f"✅ Order placed!\n\n📦 Order ID: {order['orderId']}\n\n🛒 Items:\n{lines}\n\n"
        f"💰 Total: ₹{order.get('totalAmount', 0)}\n"
        f"🚚 {'Delivery' if order.get('orderType') == 'DELIVERY' else 'Pickup'}"
    )
    if payload.get("locationPinNeeded"):
        text += "\n\n📍 Please share your live location (attachment icon → Location) so we can deliver it."
    text += f"\n\n🙏 Thank you for ordering with {restaurant.get('name', '')}."
    return text
