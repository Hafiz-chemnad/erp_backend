from datetime import datetime, timezone
from bson import ObjectId
from app.order_assignments.models import AssignOrderRequest, UpdateAssignmentStatusRequest


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def _serialize(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "restaurant_id": doc["restaurant_id"],
        "order_id": doc["order_id"],
        "display_id": doc.get("display_id", ""),
        "delivery_boy_phone": doc["delivery_boy_phone"],
        "delivery_boy_name": doc.get("delivery_boy_name", ""),
        "customer_number": doc.get("customer_number", ""),
        "delivery_status": doc.get("delivery_status", "assigned"),
        "payment_method": doc.get("payment_method"),
        "order_snapshot": doc.get("order_snapshot", {}),
        "assigned_at": _iso(doc.get("assigned_at")),
        "accepted_at": _iso(doc.get("accepted_at")),
        "picked_up_at": _iso(doc.get("picked_up_at")),
        "delivered_at": _iso(doc.get("delivered_at")),
    }


async def create_assignment(db, restaurant_id: str, order_id: str, body: AssignOrderRequest) -> dict:
    snapshot = body.order_snapshot
    doc = {
        "restaurant_id": restaurant_id,
        "order_id": order_id,
        "display_id": snapshot.get("displayId", order_id),
        "delivery_boy_phone": body.delivery_boy_phone,
        "delivery_boy_name": body.delivery_boy_name,
        "customer_number": snapshot.get("customerNumber", ""),
        "delivery_status": "assigned",
        "payment_method": None,
        "order_snapshot": snapshot,
        "masked_session_id": None,
        "assigned_at": datetime.now(timezone.utc),
        "accepted_at": None,
        "picked_up_at": None,
        "delivered_at": None,
    }
    await db.order_assignments.update_one(
        {"restaurant_id": restaurant_id, "order_id": order_id},
        {"$set": doc},
        upsert=True,
    )
    saved = await db.order_assignments.find_one({"restaurant_id": restaurant_id, "order_id": order_id})
    return _serialize(saved)


async def list_assignments_for_restaurant(db, restaurant_id: str) -> list[dict]:
    cursor = db.order_assignments.find({"restaurant_id": restaurant_id})
    return [_serialize(doc) async for doc in cursor]


async def list_assignments_for_delivery_boy(db, restaurant_id: str, phone: str) -> list[dict]:
    cursor = db.order_assignments.find({"restaurant_id": restaurant_id, "delivery_boy_phone": phone})
    return [_serialize(doc) async for doc in cursor]


# Valid forward transitions only — prevents e.g. jumping straight to
# 'delivered' from 'assigned', or moving backwards
_VALID_TRANSITIONS = {
    "assigned": {"db_accepted"},
    "db_accepted": {"picked_up"},
    "picked_up": {"delivered"},
}


async def update_assignment_status(db, assignment_id: str, body: UpdateAssignmentStatusRequest) -> dict | None:
    existing = await db.order_assignments.find_one({"_id": ObjectId(assignment_id)})
    if not existing:
        return None

    current_status = existing.get("delivery_status", "assigned")
    allowed_next = _VALID_TRANSITIONS.get(current_status, set())
    if body.status not in allowed_next:
        raise ValueError(f"Cannot move from '{current_status}' to '{body.status}'")

    now = datetime.now(timezone.utc)
    update_fields = {"delivery_status": body.status}

    if body.status == "db_accepted":
        update_fields["accepted_at"] = now
    elif body.status == "picked_up":
        update_fields["picked_up_at"] = now
    elif body.status == "delivered":
        update_fields["delivered_at"] = now
        update_fields["payment_method"] = body.payment_method

    await db.order_assignments.update_one({"_id": ObjectId(assignment_id)}, {"$set": update_fields})
    updated = await db.order_assignments.find_one({"_id": ObjectId(assignment_id)})
    return _serialize(updated)