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
    print(f"\n🔥 RAW META WEBHOOK: {body}\n", flush=True) 
    
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
                        "status": status.get("status"),
                        "timestamp": status.get("timestamp"),
                        "errors": status.get("errors"),
                        "raw": status,
                    }
                    print(f"\n📬 WA STATUS: {doc}\n", flush=True)
                    
                    # 1. Save to your message events database
                    await db.message_events.update_one(
                        {"wamid": doc["wamid"]},
                        {"$push": {"history": doc}, "$set": {"latest_status": doc["status"]}},
                        upsert=True,
                    )

                    # 2. 🚀 THE FIX: OVERWRITE THE "FAKE DATA" IN THE CAMPAIGNS DATABASE!
                    if doc["status"] in ["delivered", "read"]:
                        await db.campaigns.update_one(
                            {"recipients": {"$elemMatch": {"wamid": doc["wamid"], "status": {"$ne": doc["status"]}}}},
                            {
                                "$set": {"recipients.$.status": doc["status"]},
                                "$inc": {f"{doc['status']}_count": 1}
                            }
                        )
                    elif doc["status"] == "failed":
                        # Grab the exact error message from Meta
                        error_text = doc["errors"][0].get("title", "Meta Rejected") if doc.get("errors") else "Failed"
                        
                        await db.campaigns.update_one(
                            {"recipients": {"$elemMatch": {"wamid": doc["wamid"], "status": {"$ne": "failed"}}}},
                            {
                                # Change status to failed and save the error text
                                "$set": {"recipients.$.status": "failed", "recipients.$.error": error_text},
                                # 🚀 Fix the math! Subtract 1 from Sent, Add 1 to Failed
                                "$inc": {"failed_count": 1, "sent_count": -1} 
                            }
                        )

                # --- Incoming user messages ---
                messages = value.get("messages", [])
                for msg in messages:
                    print(f"\n📩 INCOMING MSG: {msg}\n", flush=True)

    except Exception as e:
        print(f"❌ Webhook error: {e}", flush=True)

    return {"status": "received"}