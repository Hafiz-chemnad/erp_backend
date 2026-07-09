from fastapi import APIRouter, Request, Query, HTTPException
from app.db import get_database
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["webhook"])


# 🚀 STEP 1: Meta calls this ONCE when you register the webhook URL in the
# Meta App Dashboard. It must echo back "hub.challenge" exactly, or Meta
# will refuse to save your webhook URL.
@router.get("")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == settings.META_VERIFY_TOKEN:
        return int(hub_challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


# 🚀 STEP 2: Meta POSTs here every time a message status changes
# (sent -> delivered -> read, or failed with an error code/reason).
# THIS is the only authoritative source of "did it actually reach the phone."
@router.post("")
async def receive_webhook(request: Request):
    body = await request.json()
    db = get_database()

    try:
        entries = body.get("entry", [])
        for entry in entries:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})

                # --- Message status updates (sent/delivered/read/failed) ---
                statuses = value.get("statuses", [])
                for status in statuses:
                    doc = {
                        "wamid": status.get("id"),
                        "recipient_id": status.get("recipient_id"),
                        "status": status.get("status"),  # sent/delivered/read/failed
                        "timestamp": status.get("timestamp"),
                        "errors": status.get("errors"),  # <-- the actual failure reason lives here
                        "raw": status,
                    }
                    logger.info(f"📬 WA STATUS: {doc}")
                    await db.message_events.update_one(
                        {"wamid": doc["wamid"]},
                        {"$push": {"history": doc}, "$set": {"latest_status": doc["status"]}},
                        upsert=True,
                    )

                # --- Incoming user messages (optional, but useful) ---
                messages = value.get("messages", [])
                for msg in messages:
                    logger.info(f"📩 INCOMING MSG: {msg}")

    except Exception as e:
        logger.error(f"❌ Webhook processing error: {e}")

    # Always return 200 fast — Meta disables webhooks that time out or error repeatedly
    return {"status": "received"}