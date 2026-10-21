"""
Meta WhatsApp webhook — receives:
  1. GET  /webhook  -> verification handshake (unchanged from before)
  2. POST /webhook   -> incoming messages + delivery status callbacks

Incoming messages now get routed into the bot engine instead of just logged.
"""

from fastapi import APIRouter, Request, Response, Query
from app.core.config import settings
from app.db import get_database
from app.bot_engine.engine import handle_message
from app.bot_engine.meta_sender import send_text
from app.billing import service as billing_service
from app.restaurant_messages import service as rm_service
from app.ai_agent import service as ai_agent_service
from app.ai_agent.service import AgentBackendError
import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
router = APIRouter()

# One AI conversation turn can take many seconds (agent-backend cold start,
# LLM calls). Meta re-delivers a webhook it doesn't get a fast 200 for, which
# used to make the AI answer the same message several times. So:
#   1. every inbound message id is remembered and processed only once, and
#   2. AI turns run in the background so the webhook returns 200 immediately,
#      serialised per customer so two quick messages can't race on the
#      saved conversation state.
_ai_locks: dict[str, asyncio.Lock] = {}
_bg_tasks: set = set()
_dedupe_index_ready = False


async def _already_processed(db, wamid: str | None) -> bool:
    """True if this WhatsApp message id was handled before (Meta retry)."""
    global _dedupe_index_ready
    if not wamid:
        return False
    try:
        if not _dedupe_index_ready:
            await db.processed_messages.create_index("createdAt", expireAfterSeconds=86400)
            await db.processed_messages.create_index("wamid", unique=True)
            _dedupe_index_ready = True
        res = await db.processed_messages.update_one(
            {"wamid": wamid},
            {"$setOnInsert": {"createdAt": datetime.now(timezone.utc)}},
            upsert=True,
        )
        return res.matched_count > 0
    except Exception:
        logger.exception("message de-duplication failed — processing anyway")
        return False


async def _run_ai_turn(db, restaurant, msg, customer_number, message_type, phone_number_id):
    """One AI conversation turn (text / voice note / location pin). Runs as a
    background task; never raises."""
    lock = _ai_locks.setdefault(f"{restaurant['_id']}:{customer_number}", asyncio.Lock())
    async with lock:
            rid = str(restaurant["_id"])
            wa_token = restaurant.get("waToken")
            try:
                if message_type == "audio":
                    # Voice note — transcribe first, then feed the
                    # transcript into the exact same chat path as
                    # typed text. No separate voice pipeline needed.
                    media_id = msg.get("audio", {}).get("id")
                    text_body = await ai_agent_service.transcribe_voice_note(media_id, wa_token)
                    if not text_body:
                        await send_text(
                            phone_number_id, customer_number,
                            "Sorry, I couldn't understand that voice note — could you type your order instead?",
                            wa_token,
                        )
                        return
                elif message_type == "location":
                    # The AI already asked for this pin before trying
                    # to place a DELIVERY order (see system prompt) —
                    # turn it into a plain-text turn so the model can
                    # read the coordinates and call place_order next.
                    loc = msg.get("location", {})
                    lat = loc.get("latitude")
                    lng = loc.get("longitude")
                    if lat is None or lng is None:
                        return
                    address = loc.get("address") or loc.get("name") or "not provided"
                    text_body = (
                        f"[Delivery location received] latitude={lat}, longitude={lng}, "
                        f"address={address}. Please proceed to place the order using this location."
                    )
                else:
                    text_body = msg.get("text", {}).get("body", "")

                session_state = await ai_agent_service.get_session_state(db, rid, customer_number)
                # the AI can't know who it's talking to — hand it the
                # WhatsApp number so place_order never gets a guessed one
                session_state = {**(session_state or {}), "customer_number": customer_number}
                result = await ai_agent_service.send_chat_turn(db, rid, text_body, session_state)
                await ai_agent_service.save_session_state(db, rid, customer_number, result["sessionState"])
                if result.get("response"):
                    await send_text(phone_number_id, customer_number, result["response"], wa_token)
            except AgentBackendError:
                logger.exception("ai_agent chat failed for customer %s", customer_number)
                await send_text(
                    phone_number_id, customer_number,
                    "Sorry, I'm having trouble right now — a staff member will follow up with you shortly.",
                    wa_token,
                )
            except Exception:
                logger.exception("ai_agent chat failed for customer %s", customer_number)
                try:
                    await send_text(
                        phone_number_id, customer_number,
                        "Sorry, something went wrong on our side — please send that again in a moment.",
                        wa_token,
                    )
                except Exception:
                    logger.exception("could not send failure notice to %s", customer_number)
            return


@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == settings.META_VERIFY_TOKEN:
        return Response(content=hub_challenge, media_type="text/plain")
    return Response(status_code=403)


@router.post("/webhook")
async def receive_webhook(request: Request):
    body = await request.json()
    db = get_database()

    try:
        entry = body["entry"][0]
        change = entry["changes"][0]
        value = change["value"]
        metadata = value.get("metadata", {})
        phone_number_id = metadata.get("phone_number_id")

        # ── Delivery status callbacks (sent/delivered/read/failed) ────────
        if "statuses" in value:
            for status in value["statuses"]:
                wamid = status.get("id")
                new_status = status.get("status")
                await db.message_events.update_one(
                    {"wamid": wamid},
                    {"$set": {"status": new_status, "updatedAt": datetime.now(timezone.utc)}},
                    upsert=True,
                )
            return {"ok": True}

        # ── Incoming customer messages ─────────────────────────────────
        if "messages" in value:
            restaurant = await db.restaurants.find_one({"phoneNumberId": phone_number_id})
            if not restaurant:
                return {"ok": True}  # unknown number, ignore

            for msg in value["messages"]:
                customer_number = msg["from"]
                message_type = msg.get("type", "text")

                if await _already_processed(db, msg.get("id")):
                    logger.info("duplicate webhook delivery for %s ignored", msg.get("id"))
                    continue

                # log raw inbound message (matches tymdb.messagelogs)
                await db.messagelogs.insert_one({
                    "customerId": customer_number,
                    "phoneNumberId": phone_number_id,
                    "messageType": message_type,
                    "messageText": msg.get("text", {}).get("body", "") if message_type == "text" else "",
                    "rawMessage": msg,
                    "createdAt": datetime.now(timezone.utc),
                })

                # log to chat thread (matches tymdb.usermessagelogs)
                content = msg.get("text", {}).get("body") if message_type == "text" else msg.get(message_type, {})
                await rm_service.store_message({
                    "restaurantId": str(restaurant["_id"]),
                    "customerNumber": customer_number,
                    "phoneNumberId": phone_number_id,
                    "customerId": customer_number,
                    "direction": "inbound",
                    "messageType": message_type,
                    "messageContent": content,
                })

                # ── Phone-order delivery location pin ──────────────────
                # A location message from a customer who has a phone-delivery
                # order awaiting their pin gets matched and attached here,
                # BEFORE the bot engine sees it — this is deliberately
                # separate from the bot's own scripted "location" step so
                # the normal WhatsApp bot-ordering flow is untouched.
                if message_type == "location":
                    try:
                        pending = await billing_service.find_pending_location_request(
                            db, str(restaurant["_id"]), customer_number
                        )
                        if pending:
                            loc = msg.get("location", {})
                            lat = loc.get("latitude")
                            lng = loc.get("longitude")
                            if lat is not None and lng is not None:
                                await billing_service.attach_location_and_confirm(
                                    db, str(restaurant["_id"]), pending["orderId"], lat, lng, loc.get("address")
                                )
                                await billing_service.clear_pending_location_request(
                                    db, str(restaurant["_id"]), customer_number
                                )
                                await send_text(
                                    phone_number_id, customer_number,
                                    "Location received ✅ Your order is confirmed and will be delivered soon!",
                                    restaurant.get("waToken"),
                                )
                            continue  # don't also hand this message to the bot engine
                    except Exception:
                        # a failure here shouldn't break the rest of the webhook —
                        # fall through to normal bot handling below
                        logger.exception("phone-order location handling failed for %s", customer_number)

                # ── AI agent mode (Group D) ─────────────────────────────
                # Restaurants with AI mode on get routed here instead of the
                # scripted bot — text, voice notes, and the customer's shared
                # location pin (asked for BEFORE the AI places a DELIVERY
                # order — see assemble_system_prompt) all land here.
                # Everything else in this webhook, and every restaurant that
                # hasn't turned AI mode on, is completely untouched.
                if message_type in ("text", "audio", "location") and restaurant.get("aiAgentEnabled"):
                    task = asyncio.create_task(
                        _run_ai_turn(db, restaurant, msg, customer_number, message_type, phone_number_id)
                    )
                    _bg_tasks.add(task)
                    task.add_done_callback(_bg_tasks.discard)
                    continue  # webhook answers Meta right away; the AI turn runs in the background

                # hand off to the bot engine — a single failed send inside
                # the bot flow shouldn't 500 the whole webhook (Meta would
                # otherwise retry and reprocess this message repeatedly)
                try:
                    await handle_message(restaurant, msg, customer_number)
                except Exception:
                    logger.exception("bot_engine failed for customer %s", customer_number)

        return {"ok": True}

    except (KeyError, IndexError):
        # malformed/unexpected payload shape — ignore rather than 500
        return {"ok": True}