import logging
from datetime import datetime, timezone
from app.menu.schemas import MenuItemIn, MenuItemOut, MenuListResponse, MenuItemWrite
from app.menu import meta_client

logger = logging.getLogger(__name__)

COLLECTION = "menu_items"


async def list_menu_items(db, restaurant_id: str, page: int = 1, limit: int = 50) -> MenuListResponse:
    coll = db[COLLECTION]
    skip = (page - 1) * limit

    total_count = await coll.count_documents({"restaurant_id": restaurant_id})
    total_pages = max(1, (total_count + limit - 1) // limit)

    cursor = (
        coll.find({"restaurant_id": restaurant_id})
        .sort([("category", 1), ("name", 1)])
        .skip(skip)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)
    items = [MenuItemOut(**doc) for doc in docs]
    return MenuListResponse(items=items, totalPages=total_pages, page=page)


async def _push_to_meta_best_effort(item: MenuItemOut, catalog_id: str | None, access_token: str | None) -> None:
    """Fire-and-log Meta push. Never raises — a Meta failure must not roll
    back or block the Mongo write, which already succeeded by the time
    this is called."""
    if not catalog_id or not access_token:
        return
    try:
        ok = await meta_client.push_item_to_meta(
            retailer_id=item.retailerId,
            name=item.name,
            price=item.price,
            catalog_id=catalog_id,
            access_token=access_token,
            image_url=item.imageUrl,
            description=item.category,
            is_available=item.isAvailable,
        )
        if not ok:
            logger.warning("Meta push failed for retailer_id=%s", item.retailerId)
    except Exception:
        logger.exception("Meta push exception for retailer_id=%s", item.retailerId)


async def upsert_menu_item(db, restaurant_id: str, item: MenuItemWrite) -> MenuItemOut:
    coll = db[COLLECTION]
    now = datetime.now(timezone.utc)

    # Split out the Meta credentials — they're not menu fields, don't store them
    menu_fields = MenuItemIn(**item.model_dump(exclude={"catalog_id", "access_token"}))
    doc = menu_fields.model_dump()
    doc["restaurant_id"] = restaurant_id
    doc["updated_at"] = now

    await coll.update_one(
        {"restaurant_id": restaurant_id, "retailer_id": item.retailer_id},
        {"$set": doc},
        upsert=True,
    )
    saved = await coll.find_one(
        {"restaurant_id": restaurant_id, "retailer_id": item.retailer_id}
    )
    result = MenuItemOut(**saved)

    # Mongo write already succeeded — Meta push is best-effort, after the fact
    await _push_to_meta_best_effort(result, item.catalog_id, item.access_token)

    return result


async def update_menu_item(
    db, restaurant_id: str, retailer_id: str, fields: dict,
    catalog_id: str | None = None, access_token: str | None = None,
) -> MenuItemOut | None:
    coll = db[COLLECTION]
    fields = dict(fields)  # don't mutate caller's dict
    fields["updated_at"] = datetime.now(timezone.utc)
    await coll.update_one(
        {"restaurant_id": restaurant_id, "retailer_id": retailer_id},
        {"$set": fields},
    )
    saved = await coll.find_one(
        {"restaurant_id": restaurant_id, "retailer_id": retailer_id}
    )
    if not saved:
        return None

    result = MenuItemOut(**saved)
    await _push_to_meta_best_effort(result, catalog_id, access_token)
    return result


async def delete_menu_item(
    db, restaurant_id: str, retailer_id: str,
    catalog_id: str | None = None, access_token: str | None = None,
) -> bool:
    coll = db[COLLECTION]
    result = await coll.delete_one(
        {"restaurant_id": restaurant_id, "retailer_id": retailer_id}
    )
    deleted = result.deleted_count > 0

    if deleted and catalog_id and access_token:
        try:
            ok = await meta_client.delete_item_from_meta(retailer_id, catalog_id, access_token)
            if not ok:
                logger.warning("Meta delete failed for retailer_id=%s", retailer_id)
        except Exception:
            logger.exception("Meta delete exception for retailer_id=%s", retailer_id)

    return deleted


async def sync_menu_from_meta(db, restaurant_id: str, catalog_id: str, access_token: str) -> int:
    """Pulls the full Meta catalog and upserts every item into Mongo.
    This is the ONLY place Meta -> Mongo seeding happens; Flutter never
    talks to Meta directly anymore."""
    coll = db[COLLECTION]
    meta_items = await meta_client.fetch_catalog_from_meta(catalog_id, access_token)

    synced = 0
    now = datetime.now(timezone.utc)

    for meta_item in meta_items:
        retailer_id = meta_item.get("retailer_id") or meta_item.get("id")
        if not retailer_id:
            continue

        raw_price = str(meta_item.get("price", "0"))
        cleaned_price = "".join(c for c in raw_price if c.isdigit() or c == ".")
        try:
            price = float(cleaned_price) if cleaned_price else 0.0
        except ValueError:
            price = 0.0

        # 🚀 FIX: only use Meta's image_url to SEED an item that has no
        # image yet. Meta's returned image_url on catalog reads can be a
        # temporary CDN mirror that expires — overwriting an already-set
        # image on every sync silently breaks good images over time.
        existing = await coll.find_one(
            {"restaurant_id": restaurant_id, "retailer_id": retailer_id},
            {"image_url": 1},
        )
        existing_image_url = existing.get("image_url") if existing else None

        doc = {
            "restaurant_id": restaurant_id,
            "retailer_id": retailer_id,
            "name": meta_item.get("name") or "Unnamed Item",
            "price": price,
            "category": meta_item.get("description") or "Menu Item",
            "is_available": meta_item.get("availability") == "in stock",
            "is_veg": False,
            "updated_at": now,
        }
        if not existing_image_url:
            doc["image_url"] = meta_item.get("image_url") or ""

        await coll.update_one(
            {"restaurant_id": restaurant_id, "retailer_id": retailer_id},
            {"$set": doc},
            upsert=True,
        )
        synced += 1

    return synced