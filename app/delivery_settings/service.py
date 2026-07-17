from app.delivery_settings.models import DeliverySettingsOut, DeliverySettingsUpdate

COLLECTION = "restaurant_delivery_settings"

# Defaults used whenever a restaurant hasn't set anything yet — read path
# returns these without needing a DB row to exist first.
_DEFAULTS = {
    "send_pickup_message": False,
    "send_delivered_message": True,
}


async def get_settings(db, restaurant_id: str) -> DeliverySettingsOut:
    coll = db[COLLECTION]
    doc = await coll.find_one({"restaurant_id": restaurant_id})

    if not doc:
        return DeliverySettingsOut(restaurant_id=restaurant_id, **_DEFAULTS)

    return DeliverySettingsOut(
        restaurant_id=restaurant_id,
        send_pickup_message=doc.get("send_pickup_message", _DEFAULTS["send_pickup_message"]),
        send_delivered_message=doc.get("send_delivered_message", _DEFAULTS["send_delivered_message"]),
    )


async def update_settings(db, restaurant_id: str, body: DeliverySettingsUpdate) -> DeliverySettingsOut:
    coll = db[COLLECTION]

    # Only set fields that were actually provided — lets the restaurant app
    # flip one switch without clobbering the other.
    update_fields = {}
    if body.send_pickup_message is not None:
        update_fields["send_pickup_message"] = body.send_pickup_message
    if body.send_delivered_message is not None:
        update_fields["send_delivered_message"] = body.send_delivered_message

    if update_fields:
        await coll.update_one(
            {"restaurant_id": restaurant_id},
            {"$set": update_fields, "$setOnInsert": {"restaurant_id": restaurant_id}},
            upsert=True,
        )

    return await get_settings(db, restaurant_id)