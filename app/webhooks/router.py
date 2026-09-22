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
from datetime import datetime, timezone

router = APIRouter()


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
                        pass

                # hand off to the bot engine — a single failed send inside
                # the bot flow shouldn't 500 the whole webhook (Meta would
                # otherwise retry and reprocess this message repeatedly)
                try:
                    await handle_message(restaurant, msg, customer_number)
                except Exception:
                    pass

        return {"ok": True}

    except (KeyError, IndexError):
        # malformed/unexpected payload shape — ignore rather than 500
        return {"ok": True}