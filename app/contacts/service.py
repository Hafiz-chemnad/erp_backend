from datetime import datetime, timezone
from pymongo import UpdateOne
from app.contacts.schemas import (
    ContactIn, ContactBulkIn, ContactLabelsUpdate,
    ContactOut, ContactListResponse, ContactBulkResult,
)

COLLECTION = "contacts"
LABELS_COLLECTION = "labels"


def _is_placeholder_name(name: str, phone: str) -> bool:
    """A contact's name counts as a placeholder if it's empty or literally
    just the phone number — the default the app fills in today when a
    contact is auto-created (e.g. an inbound WhatsApp sender) or added
    manually with no name typed in."""
    return (not name) or (name.strip() == phone)


async def list_contacts(db, restaurant_id: str, page: int = 1, limit: int = 50) -> ContactListResponse:
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
    items = [ContactOut(**doc) for doc in docs]
    return ContactListResponse(items=items, totalPages=total_pages, page=page)


async def upsert_contact(db, restaurant_id: str, contact: ContactIn, source: str = "manual") -> ContactOut:
    """Option B (enrichment): a re-add with the same phone never creates a
    duplicate document (phone is the unique key). If the contact already
    exists:
      - name is only overwritten if the EXISTING name was a placeholder
        (empty or == phone) and the new name is a real name. A contact
        that already has a real name never gets silently renamed by a
        later import/add.
      - source is set once on first creation and never overwritten —
        it records how the contact genuinely first appeared.
      - status/label_ids are left untouched here; labels are managed via
        the dedicated labels endpoint so a bare re-add can't wipe them.
    """
    coll = db[COLLECTION]
    now = datetime.now(timezone.utc)
    phone = contact.phone.strip()
    incoming_name = contact.name.strip() or phone

    existing = await coll.find_one({"restaurant_id": restaurant_id, "phone": phone})

    if existing is None:
        doc = {
            "restaurant_id": restaurant_id,
            "phone": phone,
            "name": incoming_name,
            "status": contact.status,
            "label_ids": [],
            "source": source,
            "created_at": now,
        }
        await coll.insert_one(doc)
        return ContactOut(**doc)

    update_fields = {}
    if _is_placeholder_name(existing.get("name", ""), phone) and incoming_name != phone:
        update_fields["name"] = incoming_name

    if update_fields:
        await coll.update_one(
            {"restaurant_id": restaurant_id, "phone": phone},
            {"$set": update_fields},
        )
        existing.update(update_fields)

    return ContactOut(**existing)


async def bulk_import_contacts(db, restaurant_id: str, body: ContactBulkIn) -> ContactBulkResult:
    """Bulk CSV import. Runs duplicate-checking against Mongo directly
    (not a client-side cache), and applies the same Option B enrichment
    rule per-row. Uses a single bulk_write for the actual DB round-trip;
    the enrichment decision (does the existing name need updating?) still
    needs a per-phone read first since it depends on current state.
    """
    coll = db[COLLECTION]
    now = datetime.now(timezone.utc)

    added = 0
    enriched = 0
    duplicate = 0
    invalid = 0
    seen_in_file = set()

    # Pull all existing phones for this restaurant once, instead of one
    # find_one per row — cheap for realistic contact-list sizes and avoids
    # N sequential queries for a large CSV.
    existing_docs = await coll.find(
        {"restaurant_id": restaurant_id},
        {"phone": 1, "name": 1},
    ).to_list(length=None)
    existing_by_phone = {d["phone"]: d for d in existing_docs}

    operations = []

    for row in body.rows:
        phone = "".join(ch for ch in row.phone if ch.isdigit())
        name = row.name.strip()

        if len(phone) < 8:
            invalid += 1
            continue
        if phone in seen_in_file:
            duplicate += 1
            continue
        seen_in_file.add(phone)

        incoming_name = name or phone
        existing = existing_by_phone.get(phone)

        if existing is None:
            operations.append(UpdateOne(
                {"restaurant_id": restaurant_id, "phone": phone},
                {"$setOnInsert": {
                    "restaurant_id": restaurant_id,
                    "phone": phone,
                    "name": incoming_name,
                    "status": "Active",
                    "label_ids": [],
                    "source": "csv_import",
                    "created_at": now,
                }},
                upsert=True,
            ))
            added += 1
        elif _is_placeholder_name(existing.get("name", ""), phone) and incoming_name != phone:
            operations.append(UpdateOne(
                {"restaurant_id": restaurant_id, "phone": phone},
                {"$set": {"name": incoming_name}},
            ))
            enriched += 1
        else:
            duplicate += 1

    if operations:
        await coll.bulk_write(operations, ordered=False)

    return ContactBulkResult(added=added, enriched=enriched, duplicate=duplicate, invalid=invalid)


async def update_contact_labels(db, restaurant_id: str, phone: str, body: ContactLabelsUpdate):
    """Full-replacement of a contact's label_ids. Returns 'not_found' if the
    phone doesn't exist, otherwise the updated ContactOut. Label existence
    isn't validated here — a stale label_id left over after a label delete
    is already handled by the labels module's $pull on delete, so this
    stays a simple set operation."""
    coll = db[COLLECTION]

    existing = await coll.find_one({"restaurant_id": restaurant_id, "phone": phone})
    if existing is None:
        return "not_found"

    await coll.update_one(
        {"restaurant_id": restaurant_id, "phone": phone},
        {"$set": {"label_ids": body.label_ids}},
    )
    saved = await coll.find_one({"restaurant_id": restaurant_id, "phone": phone})
    return ContactOut(**saved)


async def delete_contact(db, restaurant_id: str, phone: str) -> None:
    coll = db[COLLECTION]
    await coll.delete_one({"restaurant_id": restaurant_id, "phone": phone})