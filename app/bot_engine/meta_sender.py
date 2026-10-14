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


async def download_whatsapp_media(media_id: str, wa_token: str) -> tuple[bytes, str] | None:
    """Downloads a WhatsApp media attachment (e.g. a voice note) given its
    media id. Two-step Graph API flow: first resolve the media id to a
    short-lived CDN URL, then fetch the bytes from that URL — both requests
    need the same bearer token. Returns (bytes, mime_type), or None on any
    failure (caller should fall back gracefully, never crash the webhook)."""
    headers = {"Authorization": f"Bearer {wa_token}"}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            meta_resp = await client.get(f"{settings.META_GRAPH_URL}/{media_id}", headers=headers)
            if meta_resp.status_code >= 400:
                print("META MEDIA LOOKUP ERROR:", meta_resp.status_code, meta_resp.text)
                return None
            media_info = meta_resp.json()
            media_url = media_info.get("url")
            mime_type = media_info.get("mime_type", "audio/ogg")
            if not media_url:
                return None

            file_resp = await client.get(media_url, headers=headers)
            if file_resp.status_code >= 400:
                print("META MEDIA DOWNLOAD ERROR:", file_resp.status_code)
                return None
            return file_resp.content, mime_type
    except Exception as e:
        print("META MEDIA DOWNLOAD EXCEPTION:", e)
        return None