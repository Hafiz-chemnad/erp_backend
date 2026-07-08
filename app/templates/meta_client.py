import httpx
import re

GRAPH_BASE = "https://graph.facebook.com/v19.0"

async def create_template_in_meta(waba_id: str, access_token: str, name: str, category: str, language: str, body_text: str) -> dict | None:
    url = f"{GRAPH_BASE}/{waba_id}/message_templates"
    
    # 🚀 BULLETPROOF VARIABLE COUNT: Finds the highest number used (e.g., {{1}} = 1)
    # This prevents crashes if a user repeats a variable like "Hi {{1}}, your code is {{1}}"
    var_matches = re.findall(r'\{\{(\d+)\}\}', body_text)
    var_count = 0
    if var_matches:
        var_count = max([int(num) for num in var_matches])
    
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
            
            # 🚀 CRITICAL DEBUGGING: Print EXACTLY what Meta complains about!
            if response.status_code not in [200, 201]:
                print(f"❌ META REJECTED CREATE: {response.text}")
                return None
                
            return response.json()
    except Exception as e:
        print(f"❌ CREATE CRASHED: {str(e)}")
        return None

async def fetch_templates_from_meta(waba_id: str, access_token: str) -> list[dict]:
    url = f"{GRAPH_BASE}/{waba_id}/message_templates?fields=id,name,status,category,language,components,rejected_reason&limit=200"
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