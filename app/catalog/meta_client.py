"""
Push menu items to Meta's WhatsApp product catalog, and send
catalog-based product/menu messages to customers.
Same pattern as app/menu/meta_client.py.
"""

import httpx
from app.core.config import settings


async def upload_catalog_item(catalog_id: str, item: dict, wa_token: str):
    url = f"{settings.META_GRAPH_URL}/{catalog_id}/products"
    headers = {"Authorization": f"Bearer {wa_token}"}
    payload = {
        "retailer_id": item["retailer_id"],
        "name": item["name"],
        "price": f"{item['price']} INR",
        "availability": item.get("availability", "in stock"),
        "image_url": item.get("image_url", ""),
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, data=payload)
        resp.raise_for_status()
        return resp.json()


async def send_single_product(phone_number_id: str, to: str, catalog_id: str, retailer_id: str, wa_token: str):
    url = f"{settings.META_GRAPH_URL}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {wa_token}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "product",
            "body": {"text": "Here's the item you asked about:"},
            "action": {"catalog_id": catalog_id, "product_retailer_id": retailer_id},
        },
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()


async def send_product_list(phone_number_id: str, to: str, catalog_id: str, sections: list, wa_token: str):
    """sections = [{"title": "Starters", "product_items": [{"product_retailer_id": "..."}]}]"""
    url = f"{settings.META_GRAPH_URL}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {wa_token}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "product_list",
            "header": {"type": "text", "text": "Our Menu"},
            "body": {"text": "Choose what you'd like to order"},
            "action": {"catalog_id": catalog_id, "sections": sections},
        },
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            print("META API ERROR:", resp.status_code, resp.text)
        resp.raise_for_status()
        return resp.json()