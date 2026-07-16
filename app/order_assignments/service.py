from datetime import datetime, timezone
from bson import ObjectId
from app.order_assignments.models import AssignOrderRequest


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
        "order_snapshot": doc.get("order_snapshot", {}),
        "assigned_at": doc["assigned_at"].isoformat(),
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

    # Upsert — reassigning the same order replaces the previous assignment
    await db.order_assignments.update_one(
        {"restaurant_id": restaurant_id, "order_id": order_id},
        {"$set": doc},
        upsert=True,
    )
    saved = await db.order_assignments.find_one(
        {"restaurant_id": restaurant_id, "order_id": order_id}
    )
    return _serialize(saved)


async def list_assignments_for_restaurant(db, restaurant_id: str) -> list[dict]:
    cursor = db.order_assignments.find({"restaurant_id": restaurant_id})
    return [_serialize(doc) async for doc in cursor]


async def list_assignments_for_delivery_boy(db, restaurant_id: str, phone: str) -> list[dict]:
    cursor = db.order_assignments.find({
        "restaurant_id": restaurant_id,
        "delivery_boy_phone": phone,
    })
    return [_serialize(doc) async for doc in cursor]