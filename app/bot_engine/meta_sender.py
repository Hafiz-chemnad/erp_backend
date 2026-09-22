"""Sends the bot's replies back to the customer via Meta Graph API."""

import httpx
from app.core.config import settings


async def _post(phone_number_id: str, wa_token: str, payload: dict):
    url = f"{settings.META_GRAPH_URL}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {wa_token}", "Content-Type": "application/json"}
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            print("META SEND ERROR:", resp.status_code, resp.text)
        resp.raise_for_status()
        return resp.json()


async def send_text(phone_number_id: str, to: str, text: str, wa_token: str):
    return await _post(phone_number_id, wa_token, {
        "messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text},
    })


async def send_buttons(phone_number_id: str, to: str, text: str, options: list[str], wa_token: str):
    buttons = [{"type": "reply", "reply": {"id": opt, "title": opt[:20]}} for opt in options[:3]]
    return await _post(phone_number_id, wa_token, {
        "messaging_product": "whatsapp", "to": to, "type": "interactive",
        "interactive": {"type": "button", "body": {"text": text}, "action": {"buttons": buttons}},
    })


async def request_location(phone_number_id: str, to: str, text: str, wa_token: str):
    return await _post(phone_number_id, wa_token, {
        "messaging_product": "whatsapp", "to": to, "type": "interactive",
        "interactive": {"type": "location_request_message", "body": {"text": text},
                         "action": {"name": "send_location"}},
    })


async def send_list(phone_number_id: str, to: str, header: str, body: str, items: list[dict], wa_token: str):
    """items = [{"id": ..., "title": ..., "description": ...}], max 10 rows."""
    rows = [
        {"id": i["id"], "title": i["title"][:24], "description": i.get("description", "")[:72]}
        for i in items[:10]
    ]
    return await _post(phone_number_id, wa_token, {
        "messaging_product": "whatsapp", "to": to, "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": header[:60]},
            "body": {"text": body},
            "action": {"button": "View Menu", "sections": [{"title": "Menu", "rows": rows}]},
        },
    })