from datetime import datetime, timezone
from app.labels.schemas import LabelIn, LabelUpdate, LabelOut, LabelListResponse

COLLECTION = "labels"
CONTACTS_COLLECTION = "contacts"  # shared with the contacts module — label_ids lives there


async def list_labels(db, restaurant_id: str, page: int = 1, limit: int = 50) -> LabelListResponse:
    coll = db[COLLECTION]
    skip = (page - 1) * limit

    total_count = await coll.count_documents({"restaurant_id": restaurant_id})
    total_pages = max(1, (total_count + limit - 1) // limit)

    cursor = (
        coll.find({"restaurant_id": restaurant_id})
        .sort([("created_at", -1)])
        .skip(skip)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)
    items = [LabelOut(**doc) for doc in docs]
    return LabelListResponse(items=items, totalPages=total_pages, page=page)


async def create_label(db, restaurant_id: str, label: LabelIn) -> LabelOut:
    coll = db[COLLECTION]
    now = datetime.now(timezone.utc)

    doc = label.model_dump()
    doc["restaurant_id"] = restaurant_id
    doc["contact_count"] = 0

    await coll.update_one(
        {"restaurant_id": restaurant_id, "label_id": label.label_id},
        {"$set": doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    saved = await coll.find_one({"restaurant_id": restaurant_id, "label_id": label.label_id})
    return LabelOut(**saved)


async def update_label(db, restaurant_id: str, label_id: str, body: LabelUpdate) -> LabelOut | None:
    coll = db[COLLECTION]

    existing = await coll.find_one({"restaurant_id": restaurant_id, "label_id": label_id})
    if not existing:
        return None
    if existing.get("is_automated"):
        return None  # router turns this into a 403 — automated labels aren't manually editable

    await coll.update_one(
        {"restaurant_id": restaurant_id, "label_id": label_id},
        {"$set": {"name": body.name, "description": body.description}},
    )
    saved = await coll.find_one({"restaurant_id": restaurant_id, "label_id": label_id})
    return LabelOut(**saved)


async def delete_label(db, restaurant_id: str, label_id: str) -> bool | None:
    """Returns None if the label is automated (caller turns that into 403),
    True/False for a normal delete attempt."""
    coll = db[COLLECTION]

    existing = await coll.find_one({"restaurant_id": restaurant_id, "label_id": label_id})
    if not existing:
        return False
    if existing.get("is_automated"):
        return None

    await coll.delete_one({"restaurant_id": restaurant_id, "label_id": label_id})

    # 🔧 This is the actual fix the label_id migration was for: unlinking is
    # now a direct, guaranteed operation — no more name-matching cleanup sweep.
    contacts_coll = db[CONTACTS_COLLECTION]
    await contacts_coll.update_many(
        {"restaurant_id": restaurant_id},
        {"$pull": {"label_ids": label_id}},
    )
    return True


async def recalculate_label_counts(db, restaurant_id: str) -> None:
    """Recomputes contact_count for every label from the real contacts
    collection — direct query now, no string-matching sweep needed."""
    labels_coll = db[COLLECTION]
    contacts_coll = db[CONTACTS_COLLECTION]

    label_docs = await labels_coll.find({"restaurant_id": restaurant_id}).to_list(length=None)
    for label_doc in label_docs:
        label_id = label_doc["label_id"]
        count = await contacts_coll.count_documents(
            {"restaurant_id": restaurant_id, "label_ids": label_id}
        )
        await labels_coll.update_one(
            {"restaurant_id": restaurant_id, "label_id": label_id},
            {"$set": {"contact_count": count}},
        )