"""
Talks to Meta's WhatsApp Cloud API to actually send messages.
Same pattern as app/menu/meta_client.py and app/templates/meta_client.py —
kept consistent with the rest of the codebase.
"""

import httpx
from app.core.config import settings


async def send_text_message(phone_number_id: str, to: str, text: str, wa_token: str):
    url = f"{settings.META_GRAPH_URL}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {wa_token}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()


async def send_template_message(
    phone_number_id: str,
    to: str,
    template_name: str,
    language_code: str,
    wa_token: str,
    components: list | None = None,
):
    url = f"{settings.META_GRAPH_URL}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {wa_token}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
        },
    }
    if components:
        payload["template"]["components"] = components

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()