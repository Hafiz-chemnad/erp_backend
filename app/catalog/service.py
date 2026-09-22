from app.db import get_database
from bson import ObjectId
from app.catalog import meta_client, sheet_client


async def _get_restaurant(restaurant_id: str):
    db = get_database()
    r = await db.restaurants.find_one({"_id": ObjectId(restaurant_id)})
    if not r:
        raise ValueError("Restaurant not found")
    return r


async def link_catalog(restaurant_id: str, catalog_id: str):
    db = get_database()
    await db.restaurants.update_one(
        {"_id": ObjectId(restaurant_id)}, {"$set": {"catalogId": catalog_id}}
    )
    return {"restaurantId": restaurant_id, "catalogId": catalog_id}


async def get_catalog_items(restaurant_id: str):
    restaurant = await _get_restaurant(restaurant_id)
    return restaurant.get("catalogItems", [])


async def sync_from_sheet(restaurant_id: str):
    restaurant = await _get_restaurant(restaurant_id)
    sheet_id = restaurant.get("googleSheetId")
    if not sheet_id:
        raise ValueError("No googleSheetId set on this restaurant")

    items = sheet_client.fetch_sheet_items(sheet_id)
    return await _sync_items(restaurant, items)


async def sync_catalog(restaurant_id: str):
    """Push whatever is currently in restaurant.catalogItems to Meta."""
    restaurant = await _get_restaurant(restaurant_id)
    items = restaurant.get("catalogItems", [])
    return await _sync_items(restaurant, items)


async def _sync_items(restaurant: dict, items: list[dict]):
    db = get_database()
    catalog_id = restaurant.get("catalogId")
    wa_token = restaurant["waToken"]
    if not catalog_id:
        raise ValueError("No catalogId linked to this restaurant")

    results = []
    for item in items:
        result = await meta_client.upload_catalog_item(catalog_id, item, wa_token)
        results.append(result)

    await db.restaurants.update_one(
        {"_id": restaurant["_id"]}, {"$set": {"catalogItems": items}}
    )
    return {"synced": len(items), "results": results}


async def send_product(restaurant_id: str, to: str, phone_number_id: str, retailer_id: str):
    restaurant = await _get_restaurant(restaurant_id)
    return await meta_client.send_single_product(
        phone_number_id, to, restaurant["catalogId"], retailer_id, restaurant["waToken"]
    )


async def send_menu(restaurant_id: str, to: str, phone_number_id: str):
    restaurant = await _get_restaurant(restaurant_id)
    db = get_database()

    # Pull from menu_items collection — the single source of truth, same
    # one sync-meta populates and the Flutter Menu tab already reads.
    cursor = db.menu_items.find({"restaurant_id": restaurant_id, "is_available": True})
    items = [doc async for doc in cursor]

    if not items:
        raise ValueError("No available menu items found for this restaurant")

    sections = [{
        "title": "Menu",
        "product_items": [{"product_retailer_id": i["retailer_id"]} for i in items[:30]],  # Meta caps at 30
    }]
    return await meta_client.send_product_list(
        phone_number_id, to, restaurant["catalogId"], sections, restaurant["waToken"]
    )