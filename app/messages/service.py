from app.db import get_database
from bson import ObjectId
from app.messages import meta_client
from app.restaurant_messages import service as rm_service


async def _get_wa_token(restaurant_id: str) -> str:
    db = get_database()
    restaurant = await db.restaurants.find_one({"_id": ObjectId(restaurant_id)})
    if not restaurant:
        raise ValueError("Restaurant not found")
    return restaurant["waToken"]


async def send_text(restaurant_id: str, phone_number_id: str, to: str, text: str, customer_id: str | None):
    wa_token = await _get_wa_token(restaurant_id)
    result = await meta_client.send_text_message(phone_number_id, to, text, wa_token)

    # log to chat thread (usermessagelogs) so it shows up in inbox instantly
    await rm_service.store_message({
        "restaurantId": restaurant_id,
        "customerNumber": to,
        "phoneNumberId": phone_number_id,
        "customerId": customer_id,
        "direction": "outbound",
        "messageType": "text",
        "messageContent": text,
    })
    return result


async def send_template(restaurant_id: str, phone_number_id: str, to: str, template_name: str, language_code: str, components: list | None):
    wa_token = await _get_wa_token(restaurant_id)
    result = await meta_client.send_template_message(
        phone_number_id, to, template_name, language_code, wa_token, components
    )

    await rm_service.store_message({
        "restaurantId": restaurant_id,
        "customerNumber": to,
        "phoneNumberId": phone_number_id,
        "customerId": None,
        "direction": "outbound",
        "messageType": "template",
        "messageContent": {"templateName": template_name, "components": components},
    })
    return result