import logging
from datetime import datetime, timezone
from bson import ObjectId
from bson.errors import InvalidId
from app.restaurants.schemas import RestaurantIn, RestaurantOut

logger = logging.getLogger(__name__)

COLLECTION = "restaurants"

# Fields the old Node backend sometimes stored as the literal string
# "string" (Swagger example-value leakage) instead of "" or omitting
# them. We normalize these to "" on write so new data is clean, while
# settings_screen.dart's existing `== 'string' ? '' : value` checks keep
# old/untouched records working during the transition.
_STRING_SENTINEL = "string"


def _clean(value):
    if isinstance(value, str) and value.strip() == _STRING_SENTINEL:
        return ""
    return value


def _doc_to_out(doc: dict) -> RestaurantOut:
    doc = dict(doc)
    doc["_id"] = str(doc["_id"])
    return RestaurantOut(**doc)


def _to_object_id(restaurant_id: str) -> ObjectId | None:
    try:
        return ObjectId(restaurant_id)
    except (InvalidId, TypeError):
        return None


async def list_restaurants(db) -> list[RestaurantOut]:
    coll = db[COLLECTION]
    cursor = coll.find({})
    docs = await cursor.to_list(length=None)
    return [_doc_to_out(doc) for doc in docs]


async def get_restaurant(db, restaurant_id: str) -> RestaurantOut | None:
    coll = db[COLLECTION]
    oid = _to_object_id(restaurant_id)
    if oid is None:
        return None
    doc = await coll.find_one({"_id": oid})
    if not doc:
        return None
    return _doc_to_out(doc)


async def create_restaurant(db, payload: RestaurantIn) -> RestaurantOut:
    coll = db[COLLECTION]
    now = datetime.now(timezone.utc)

    doc = {k: _clean(v) for k, v in payload.model_dump(exclude_none=True).items()}
    doc["createdAt"] = now
    doc["updatedAt"] = now

    result = await coll.insert_one(doc)
    saved = await coll.find_one({"_id": result.inserted_id})
    return _doc_to_out(saved)


async def update_restaurant(db, restaurant_id: str, payload: RestaurantIn) -> RestaurantOut | None:
    coll = db[COLLECTION]
    oid = _to_object_id(restaurant_id)
    if oid is None:
        return None

    fields = {k: _clean(v) for k, v in payload.model_dump(exclude_none=True).items()}
    if not fields:
        # Nothing to update — just return current state if it exists
        return await get_restaurant(db, restaurant_id)

    fields["updatedAt"] = datetime.now(timezone.utc)

    result = await coll.update_one({"_id": oid}, {"$set": fields})
    if result.matched_count == 0:
        return None

    saved = await coll.find_one({"_id": oid})
    return _doc_to_out(saved)