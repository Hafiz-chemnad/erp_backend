from datetime import datetime, timezone
from app.delivery_boys.schemas import DeliveryBoyIn, DeliveryBoyOut, DeliveryBoyListResponse

COLLECTION = "delivery_boys"


async def list_delivery_boys(db, restaurant_id: str, page: int = 1, limit: int = 50) -> DeliveryBoyListResponse:
    coll = db[COLLECTION]
    skip = (page - 1) * limit

    total_count = await coll.count_documents({"restaurant_id": restaurant_id})
    total_pages = max(1, (total_count + limit - 1) // limit)

    cursor = (
        coll.find({"restaurant_id": restaurant_id})
        .sort([("name", 1)])
        .skip(skip)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)
    items = [DeliveryBoyOut(**doc) for doc in docs]
    return DeliveryBoyListResponse(items=items, totalPages=total_pages, page=page)


async def add_delivery_boy(db, restaurant_id: str, boy: DeliveryBoyIn) -> DeliveryBoyOut:
    coll = db[COLLECTION]
    now = datetime.now(timezone.utc)

    doc = boy.model_dump()
    doc["restaurant_id"] = restaurant_id

    # Upsert on (restaurant_id, phone) — adding the same phone twice just
    # updates the name rather than erroring, matching the local SQLite
    # ConflictAlgorithm.ignore behaviour's intent (no duplicate phones).
    # created_at is only ever set once, on first insert.
    await coll.update_one(
        {"restaurant_id": restaurant_id, "phone": boy.phone},
        {"$set": doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    saved = await coll.find_one({"restaurant_id": restaurant_id, "phone": boy.phone})
    return DeliveryBoyOut(**saved)


async def update_delivery_boy(db, restaurant_id: str, phone: str, name: str) -> DeliveryBoyOut | None:
    coll = db[COLLECTION]
    await coll.update_one(
        {"restaurant_id": restaurant_id, "phone": phone},
        {"$set": {"name": name}},
    )
    saved = await coll.find_one({"restaurant_id": restaurant_id, "phone": phone})
    return DeliveryBoyOut(**saved) if saved else None


async def delete_delivery_boy(db, restaurant_id: str, phone: str) -> bool:
    coll = db[COLLECTION]
    result = await coll.delete_one({"restaurant_id": restaurant_id, "phone": phone})
    return result.deleted_count > 0