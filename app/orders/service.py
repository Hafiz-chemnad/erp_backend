from app.db import get_database
from bson import ObjectId
from datetime import datetime, timezone
import math


def _serialize(doc: dict) -> dict:
    """Convert Mongo's ObjectId fields to strings so FastAPI can JSON-encode them."""
    if doc:
        if "_id" in doc:
            doc["_id"] = str(doc["_id"])
        if "restaurantId" in doc:
            doc["restaurantId"] = str(doc["restaurantId"])
    return doc


async def list_orders(restaurant_id: str, status: str | None, page: int, limit: int):
    db = get_database()
    query = {"restaurantId": ObjectId(restaurant_id)}
    if status:
        query["paymentStatus"] = status

    total = await db.orders.count_documents(query)
    cursor = (
        db.orders.find(query)
        .sort("createdAt", -1)
        .skip((page - 1) * limit)
        .limit(limit)
    )
    orders = [_serialize(doc) async for doc in cursor]

    return {
        "orders": orders,
        "totalOrders": total,
        "currentPage": page,
        "totalPages": math.ceil(total / limit) if limit else 1,
    }


async def get_order_stats(restaurant_id: str):
    db = get_database()
    pipeline = [
        {"$match": {"restaurantId": ObjectId(restaurant_id)}},
        {
            "$group": {
                "_id": "$paymentStatus",
                "count": {"$sum": 1},
                "revenue": {"$sum": "$totalAmount"},
            }
        },
    ]
    rows = [r async for r in db.orders.aggregate(pipeline)]
    stats = {r["_id"]: r["count"] for r in rows}
    total_revenue = sum(r["revenue"] for r in rows)
    total_orders = sum(r["count"] for r in rows)
    return {
        "totalOrders": total_orders,
        "pending": stats.get("pending", 0),
        "accepted": stats.get("accepted", 0),
        "preparing": stats.get("preparing", 0),
        "ready": stats.get("ready", 0),
        "completed": stats.get("completed", 0),
        "rejected": stats.get("rejected", 0),
        "awaitingLocation": stats.get("awaiting_location", 0),  # phone-delivery orders waiting on a WhatsApp pin
        "merged": stats.get("merged", 0),  # table-merge closures — not a real order outcome, just bookkeeping
        "totalRevenue": total_revenue,
    }


async def get_order(order_id: str):
    db = get_database()
    order = await db.orders.find_one({"orderId": order_id})
    return _serialize(order)


async def update_order_status(order_id: str, payment_status: str, notes: str | None):
    db = get_database()
    update = {"paymentStatus": payment_status, "updatedAt": datetime.now(timezone.utc)}
    if notes is not None:
        update["additionalNotes"] = notes
    result = await db.orders.find_one_and_update(
        {"orderId": order_id}, {"$set": update}, return_document=True
    )
    return _serialize(result)


async def create_order(order_doc: dict):
    """Called by bot_engine when a WhatsApp conversation completes."""
    db = get_database()
    order_doc["createdAt"] = datetime.now(timezone.utc)
    result = await db.orders.insert_one(order_doc)
    order_doc["_id"] = result.inserted_id
    return _serialize(order_doc)