from datetime import datetime, timezone
from app.campaigns.schemas import (
    CampaignStartIn, CampaignProgressIn, CampaignOut,
    CampaignListResponse, CampaignListItemOut,
)

COLLECTION = "campaigns"


def _project_list_item(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k != "recipients"}


async def start_campaign(db, restaurant_id: str, body: CampaignStartIn) -> CampaignOut:
    """Creates the campaign record the MOMENT the user hits Launch.
    🚀 FIX: now stores media_id/media_url/button_url_param on the record
    itself, so a later Resume can read them back and pre-fill the media
    step instead of forcing a full re-upload of the same asset."""
    coll = db[COLLECTION]
    contacts_coll = db["contacts"]
    now = datetime.now(timezone.utc)
    campaign_id = f"camp_{int(now.timestamp() * 1000)}"
    
    incoming_phones = [r.phone for r in body.recipients]

    blocked_cursor = contacts_coll.find({
    "restaurant_id": restaurant_id,
    "phone": {"$in": incoming_phones},
    "status": "Blocked"
    })
    blocked_docs = await blocked_cursor.to_list(length=None)
    blocked_phones = {doc["phone"] for doc in blocked_docs}
    recipients = [
    {"phone": r.phone, "status": "pending", "error": None, "wamid": None} 
    for r in body.recipients if r.phone not in blocked_phones # 🚀 THE FILTER
    ]

    doc = {
        "restaurant_id": restaurant_id,
        "campaign_id": campaign_id,
        "name": body.name,
        "template_name": body.template_name,
        "audience_type": body.audience_type,
        "label_id": body.label_id,
        "recipients_count": len(recipients),
        "sent_count": 0,
        "failed_count": 0,
        "delivered_count": 0,
        "read_count": 0,
        "status": "sending" if len(recipients) > 0 else "completed",
        "recipients": recipients,
        "media_id": body.media_id,
        "media_url": body.media_url,
        "button_url_param": body.button_url_param,
        "created_at": now,
    }
    await coll.insert_one(doc)
    return CampaignOut(**doc)


async def report_progress(db, restaurant_id: str, campaign_id: str, body: CampaignProgressIn):
    coll = db[COLLECTION]
    existing = await coll.find_one({"restaurant_id": restaurant_id, "campaign_id": campaign_id})
    if existing is None:
        return "not_found"
    if existing.get("status") == "cancelled":
        return "cancelled"

    update_query = {
        "$set": {"recipients.$.status": body.outcome, "recipients.$.error": body.error, "recipients.$.wamid": body.wamid}
    }
    if body.outcome == "failed":
        update_query["$inc"] = {"failed_count": 1}

    await coll.update_one(
        {"restaurant_id": restaurant_id, "campaign_id": campaign_id, "recipients.phone": body.phone},
        update_query
    )

    updated = await coll.find_one({"restaurant_id": restaurant_id, "campaign_id": campaign_id})

    processed_count = sum(1 for r in updated["recipients"] if r.get("wamid") or r["status"] == "failed")

    if updated["status"] == "sending" and processed_count >= updated["recipients_count"]:
        final_status = "completed" if updated["failed_count"] == 0 else "partial"
        if processed_count == updated["failed_count"]:
            final_status = "failed"

        await coll.update_one(
            {"restaurant_id": restaurant_id, "campaign_id": campaign_id},
            {"$set": {"status": final_status}},
        )
        updated["status"] = final_status

    return CampaignOut(**updated)


async def cancel_campaign(db, restaurant_id: str, campaign_id: str):
    coll = db[COLLECTION]
    existing = await coll.find_one({"restaurant_id": restaurant_id, "campaign_id": campaign_id})
    if existing is None:
        return "not_found"
    if existing.get("status") != "sending":
        return "not_active"

    await coll.update_one(
        {"restaurant_id": restaurant_id, "campaign_id": campaign_id},
        {"$set": {"status": "cancelled"}},
    )
    updated = await coll.find_one({"restaurant_id": restaurant_id, "campaign_id": campaign_id})
    return CampaignOut(**updated)


async def delete_campaign(db, restaurant_id: str, campaign_id: str):
    coll = db[COLLECTION]
    existing = await coll.find_one({"restaurant_id": restaurant_id, "campaign_id": campaign_id})
    if existing is None:
        return "not_found"
    if existing.get("status") == "sending":
        return "forbidden"

    await coll.delete_one({"restaurant_id": restaurant_id, "campaign_id": campaign_id})
    return "ok"


async def list_campaigns(db, restaurant_id: str, page: int = 1, limit: int = 50) -> CampaignListResponse:
    coll = db[COLLECTION]
    skip = (page - 1) * limit

    total_count = await coll.count_documents({"restaurant_id": restaurant_id})
    total_pages = max(1, (total_count + limit - 1) // limit)

    cursor = (
        coll.find({"restaurant_id": restaurant_id}, {"recipients": 0})
        .sort([("created_at", -1)])
        .skip(skip)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)
    items = [CampaignListItemOut(**doc) for doc in docs]
    return CampaignListResponse(items=items, totalPages=total_pages, page=page)


async def get_campaign(db, restaurant_id: str, campaign_id: str):
    coll = db[COLLECTION]
    doc = await coll.find_one({"restaurant_id": restaurant_id, "campaign_id": campaign_id})
    if doc is None:
        return "not_found"
    return CampaignOut(**doc)


async def resume_campaign(db, restaurant_id: str, campaign_id: str):
    coll = db[COLLECTION]
    existing = await coll.find_one({"restaurant_id": restaurant_id, "campaign_id": campaign_id})
    if existing is None:
        return "not_found"
    if existing.get("status") not in ["cancelled", "partial"]:
        return "invalid_state"

    await coll.update_one(
        {"restaurant_id": restaurant_id, "campaign_id": campaign_id},
        {"$set": {"status": "sending"}},
    )
    updated = await coll.find_one({"restaurant_id": restaurant_id, "campaign_id": campaign_id})
    return CampaignOut(**updated)