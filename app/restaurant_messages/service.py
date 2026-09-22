from app.db import get_database
from datetime import datetime
import math
from datetime import timezone

def _serialize(doc: dict) -> dict:
    """Convert Mongo's ObjectId _id to a string so FastAPI can JSON-encode it."""
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def store_message(data: dict):
    db = get_database()
    data["timestamp"] = datetime.now(timezone.utc)
    result = await db.usermessagelogs.insert_one(data)
    data["_id"] = str(result.inserted_id)
    return data


async def get_thread(restaurant_id: str, customer_number: str, page: int, limit: int):
    db = get_database()
    query = {"restaurantId": restaurant_id, "customerNumber": customer_number}

    total = await db.usermessagelogs.count_documents(query)
    cursor = (
        db.usermessagelogs.find(query)
        .sort("timestamp", -1)
        .skip((page - 1) * limit)
        .limit(limit)
    )
    messages = [_serialize(doc) async for doc in cursor]

    return {
        "messages": messages,
        "totalMessages": total,
        "currentPage": page,
        "totalPages": math.ceil(total / limit) if limit else 1,
    }


async def get_restaurant_messages(restaurant_id: str, direction: str | None, page: int, limit: int):
    db = get_database()
    query = {"restaurantId": restaurant_id}
    if direction:
        query["direction"] = direction

    total = await db.usermessagelogs.count_documents(query)
    cursor = (
        db.usermessagelogs.find(query)
        .sort("timestamp", -1)
        .skip((page - 1) * limit)
        .limit(limit)
    )
    messages = [_serialize(doc) async for doc in cursor]

    return {
        "messages": messages,
        "totalMessages": total,
        "currentPage": page,
        "totalPages": math.ceil(total / limit) if limit else 1,
    }