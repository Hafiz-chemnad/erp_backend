from datetime import datetime, timezone
from pymongo import UpdateOne
from pymongo import InsertOne, UpdateOne
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
    # Sanitize to digits-only here too — bulk_import_contacts already does
    # this, but single-add was trusting the client to have stripped
    # formatting first. Without this, "+91 98765" and "919876500000" could
    # end up as two different documents instead of merging into one.
    phone = "".join(ch for ch in contact.phone if ch.isdigit())
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

    # 🚀 ADD THIS: Allow the status to be updated (Blocked <-> Active)
    if existing.get("status") != contact.status:
        update_fields["status"] = contact.status    

    if update_fields:
        await coll.update_one(
            {"restaurant_id": restaurant_id, "phone": phone},
            {"$set": update_fields},
        )
        existing.update(update_fields)

    return ContactOut(**existing)


async def bulk_import_contacts(db, restaurant_id: str, body: ContactBulkIn) -> ContactBulkResult:
    coll = db[COLLECTION]
    labels_coll = db[LABELS_COLLECTION] # 🚀 NEW: We need to check/create labels
    now = datetime.now(timezone.utc)
    
    added = 0
    enriched = 0
    duplicate = 0
    invalid = 0

    operations = []

    for row in body.rows:
        phone = "".join(filter(str.isdigit, row.phone))
        if not phone or len(phone) < 8:
            invalid += 1
            continue

        incoming_name = row.name.strip()
        
        # =========================================================
        # 🚀 THE LABEL LOGIC: Find or Dynamically Create the Label
        # =========================================================
        label_id_to_add = None
        if row.label:
            label_name = row.label.strip()
            if label_name:
                existing_label = await labels_coll.find_one({"restaurant_id": restaurant_id, "name": label_name})
                if existing_label:
                    label_id_to_add = existing_label["label_id"]
                else:
                    new_label_id = f"lbl_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
                    await labels_coll.insert_one({
                        "restaurant_id": restaurant_id,
                        "label_id": new_label_id,
                        "name": label_name,
                        "description": "Imported via CSV",
                        "contact_count": 0,
                        "is_automated": False,
                        "created_at": now
                    })
                    label_id_to_add = new_label_id
        # =========================================================

        existing = await coll.find_one({"restaurant_id": restaurant_id, "phone": phone})
        if existing is None:
            operations.append(InsertOne({
                "restaurant_id": restaurant_id,
                "phone": phone,
                "name": incoming_name if incoming_name else phone,
                "status": "Active",
                "label_ids": [label_id_to_add] if label_id_to_add else [], # 🚀 Attach label if it exists
                "source": "csv_import",
                "created_at": now
            }))
            added += 1
        else:
            update_doc = {}
            set_fields = {}
            
            # Enrich name if existing is a placeholder
            if _is_placeholder_name(existing.get("name", ""), phone) and incoming_name != phone:
                set_fields["name"] = incoming_name
                
            if set_fields:
                update_doc["$set"] = set_fields
                
            # 🚀 Add the label to this existing contact safely
            if label_id_to_add:
                update_doc["$addToSet"] = {"label_ids": label_id_to_add}

            if update_doc:
                operations.append(UpdateOne(
                    {"restaurant_id": restaurant_id, "phone": phone},
                    update_doc
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