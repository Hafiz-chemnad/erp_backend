import httpx
import re

GRAPH_BASE = "https://graph.facebook.com/v19.0"

async def create_template_in_meta(waba_id: str, access_token: str, name: str, category: str, language: str, body_text: str) -> dict | None:
    url = f"{GRAPH_BASE}/{waba_id}/message_templates"
    
    # Count variables using regex (e.g., {{1}}, {{2}})
    var_count = len(re.findall(r'\{\{\d+\}\}', body_text))
    
    components = [{"type": "BODY", "text": body_text}]
    
    # Meta requires dummy examples if variables exist to bypass the spam filter
    if var_count > 0:
        components[0]["example"] = {"body_text": [["Sample"] * var_count]}

    payload = {
        "name": name,
        "category": category,
        "language": language,
        "components": components
    }
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, headers={"Authorization": f"Bearer {access_token}"}, json=payload)
            if response.status_code in [200, 201]:
                return response.json()
            return None
    except Exception:
        return None

async def fetch_templates_from_meta(waba_id: str, access_token: str) -> list[dict]:
    url = f"{GRAPH_BASE}/{waba_id}/message_templates?fields=name,status,category,language,components,rejected_reason&limit=200"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, headers={"Authorization": f"Bearer {access_token}"})
            if response.status_code == 200:
                return response.json().get("data", [])
            return []
    except Exception:
        return []

async def delete_template_in_meta(waba_id: str, access_token: str, name: str) -> bool:
    url = f"{GRAPH_BASE}/{waba_id}/message_templates?name={name}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.delete(url, headers={"Authorization": f"Bearer {access_token}"})
            return response.status_code == 200
    except Exception:
        return False