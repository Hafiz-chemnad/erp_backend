from datetime import datetime, timezone
from app.campaigns.schemas import (
    CampaignStartIn, CampaignProgressIn, CampaignOut,
    CampaignListResponse, CampaignListItemOut,
)

COLLECTION = "campaigns"


def _project_list_item(doc: dict) -> dict:
    """Strips the (potentially large) recipients array for list views."""
    return {k: v for k, v in doc.items() if k != "recipients"}


async def start_campaign(db, restaurant_id: str, body: CampaignStartIn) -> CampaignOut:
    """Creates the campaign record the MOMENT the user hits Launch —
    before a single message has actually been sent. Every recipient
    starts 'pending'. This is what makes live progress possible: the
    record exists and is queryable from second one, not just at the end."""
    coll = db[COLLECTION]
    now = datetime.now(timezone.utc)
    campaign_id = f"camp_{int(now.timestamp() * 1000)}"

    recipients = [{"phone": r.phone, "status": "pending", "error": None} for r in body.recipients]

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
        "delivered_count": 0, # 🚀 ADDED
        "read_count": 0,      # 🚀 ADDED
        "status": "sending",
        "recipients": recipients,
        "created_at": now,
    }
    await coll.insert_one(doc)
    return CampaignOut(**doc)


async def report_progress(db, restaurant_id: str, campaign_id: str, body: CampaignProgressIn):
    """Called once per recipient, right after that individual send
    attempt finishes. Does an ATOMIC increment + targeted array update —
    no read-then-write, so concurrent/rapid calls from the same send loop
    can't race each other and undercount.

    Also auto-derives final status once every recipient has been
    accounted for, so the client never needs a separate 'mark complete'
    call — the loop just keeps calling this per-recipient and the last
    call naturally finalizes the record."""
    coll = db[COLLECTION]

    existing = await coll.find_one({"restaurant_id": restaurant_id, "campaign_id": campaign_id})
    if existing is None:
        return "not_found"
    if existing.get("status") == "cancelled":
        # A cancelled campaign shouldn't have its counts bumped by
        # in-flight sends that were already queued client-side before
        # the cancel flag was noticed.
        return "cancelled"

    inc_field = "sent_count" if body.outcome == "sent" else "failed_count"

    # Update the matching recipient entry in the array, and increment the
    # right counter, in one atomic operation.
    await coll.update_one(
        {"restaurant_id": restaurant_id, "campaign_id": campaign_id, "recipients.phone": body.phone},
        {
            "$set": {"recipients.$.status": body.outcome, "recipients.$.error": body.error,"recipients.$.wamid": body.wamid},
            "$inc": {inc_field: 1},
        },
    )

    updated = await coll.find_one({"restaurant_id": restaurant_id, "campaign_id": campaign_id})

    # Auto-finalize once every recipient has a non-pending status.
    total_done = updated["sent_count"] + updated["failed_count"]
    if updated["status"] == "sending" and total_done >= updated["recipients_count"]:
        if updated["failed_count"] == 0:
            final_status = "completed"
        elif updated["sent_count"] == 0:
            final_status = "failed"
        else:
            final_status = "partial"

        await coll.update_one(
            {"restaurant_id": restaurant_id, "campaign_id": campaign_id},
            {"$set": {"status": final_status}},
        )
        updated["status"] = final_status

    return CampaignOut(**updated)


async def cancel_campaign(db, restaurant_id: str, campaign_id: str):
    """Stops a campaign mid-send. Remaining 'pending' recipients are left
    as-is (they were never sent to) so the record shows exactly how far
    the campaign got before being stopped."""
    coll = db[COLLECTION]
    existing = await coll.find_one({"restaurant_id": restaurant_id, "campaign_id": campaign_id})
    if existing is None:
        return "not_found"
    if existing.get("status") != "sending":
        return "not_active"  # already finished/cancelled — nothing to stop

    await coll.update_one(
        {"restaurant_id": restaurant_id, "campaign_id": campaign_id},
        {"$set": {"status": "cancelled"}},
    )
    updated = await coll.find_one({"restaurant_id": restaurant_id, "campaign_id": campaign_id})
    return CampaignOut(**updated)


async def delete_campaign(db, restaurant_id: str, campaign_id: str):
    """Refuses to delete a campaign that's still actively sending — it
    must be cancelled first. This stops the tracking record from being
    ripped out from under an in-flight client-side send loop that's still
    calling report_progress() against it."""
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
    """Full detail including per-recipient statuses — used for a future
    'retry failed only' view, or just to inspect exactly who failed."""
    coll = db[COLLECTION]
    doc = await coll.find_one({"restaurant_id": restaurant_id, "campaign_id": campaign_id})
    if doc is None:
        return "not_found"
    return CampaignOut(**doc)