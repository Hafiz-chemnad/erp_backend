import httpx
import re

GRAPH_BASE = "https://graph.facebook.com/v19.0"

# app/templates/meta_client.py

async def create_template_in_meta(
    waba_id: str, 
    access_token: str, 
    name: str, 
    category: str, 
    language: str, 
    body_text: str,
    header_type: str = "NONE",   # 🚀 ADDED
    header_text: str | None = None  # 🚀 ADDED
) -> dict | None:
    url = f"{GRAPH_BASE}/{waba_id}/message_templates"
    
    var_matches = re.findall(r'\{\{(\d+)\}\}', body_text)
    var_count = max([int(num) for num in var_matches]) if var_matches else 0
    
    components = [{"type": "BODY", "text": body_text}]
    if var_count > 0:
        components[0]["example"] = {"body_text": [["Sample"] * var_count]}

    # 🚀 NEW HEADER LOGIC: Build and append the header component block
    if header_type in ["IMAGE", "VIDEO", "DOCUMENT"]:
        dummy_urls = {
            "IMAGE": "https://dummyimage.com/600x400/png/text=Sample",
            "VIDEO": "https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/360/Big_Buck_Bunny_360_10s_1MB.mp4",
            "DOCUMENT": "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
        }
        components.append({
            "type": "HEADER",
            "format": header_type,
            "example": {"header_handle": [dummy_urls[header_type]]}
        })
    elif header_type == "TEXT" and header_text:
        components.append({
            "type": "HEADER",
            "format": "TEXT",
            "text": header_text
        })

    payload = {
        "name": name,
        "category": category,
        "language": language,
        "components": components
    }
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, headers={"Authorization": f"Bearer {access_token}"}, json=payload)
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

async def send_template_message(
    phone_number_id: str, # Note: Meta uses phone_number_id for sending, not waba_id!
    access_token: str, 
    to_phone: str, 
    template_name: str, 
    language_code: str, 
    body_params: list[str], 
    header_type: str = "NONE", 
    media_url: str = None
) -> bool:
    
    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    
    # 1. Base Meta Sending Payload
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            "components": []
        }
    }
    
    # 2. Inject Header Component (If media exists)
    if header_type in ["IMAGE", "VIDEO", "DOCUMENT"] and media_url:
        param_type = header_type.lower()
        payload["template"]["components"].append({
            "type": "header",
            "parameters": [
                {
                    "type": param_type,
                    param_type: {"link": media_url}
                }
            ]
        })
        
    # 3. Inject Body Components (Your {{1}}, {{2}} variables)
    if body_params:
        body_parameters = [{"type": "text", "text": str(param)} for param in body_params]
        payload["template"]["components"].append({
            "type": "body",
            "parameters": body_parameters
        })
        
    # 4. Fire to Meta
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, headers={"Authorization": f"Bearer {access_token}"}, json=payload)
            if response.status_code in [200, 201]:
                return True
            else:
                print(f"❌ SEND FAILED: {response.text}")
                return False
    except Exception as e:
        print(f"❌ SEND CRASHED: {str(e)}")
        return False        