import httpx
import re

GRAPH_BASE = "https://graph.facebook.com/v19.0"

# app/templates/meta_client.py

# 🚀 NEW HELPER: Silently uploads a dummy file to Meta's Resumable API to get the required handle
async def get_dummy_media_handle(access_token: str, header_type: str) -> str | None:
    dummy_files = {
        "IMAGE": {
            # 🚀 Swapped to a highly reliable GitHub-hosted dummy image just to be safe
            "url": "https://raw.githubusercontent.com/github/explore/80688e429a7d4ef2fca1e82350fe8e3517d3494d/topics/python/python.png",
            "type": "image/png"
        },
        "VIDEO": {
            "url": "https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/360/Big_Buck_Bunny_360_10s_1MB.mp4",
            "type": "video/mp4"
        },
        "DOCUMENT": {
            "url": "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf",
            "type": "application/pdf"
        }
    }
    
    if header_type not in dummy_files:
        return None
        
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 🚀 FIX: Added a Google Chrome User-Agent disguise so servers don't block the download!
            browser_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            
            # 1. Download dummy file bytes using the disguise
            media_resp = await client.get(dummy_files[header_type]["url"], headers=browser_headers)
            if media_resp.status_code != 200:
                print(f"❌ Failed to download dummy media. Server returned Status: {media_resp.status_code}")
                return None
            
            file_bytes = media_resp.content
            
            # 2. Create Upload Session
            session_url = f"{GRAPH_BASE}/app/uploads"
            session_params = {
                "file_length": str(len(file_bytes)),
                "file_type": dummy_files[header_type]["type"]
            }
            session_resp = await client.post(
                session_url, 
                params=session_params, 
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            if session_resp.status_code != 200:
                print(f"❌ Meta Session Error: {session_resp.text}")
                return None
                
            session_id = session_resp.json().get("id")
            
            # 3. Upload File Bytes using the Session ID
            upload_url = f"{GRAPH_BASE}/{session_id}"
            upload_headers = {
                "Authorization": f"OAuth {access_token}",
                "file_offset": "0"
            }
            upload_resp = await client.post(
                upload_url, 
                headers=upload_headers, 
                content=file_bytes
            )
            
            if upload_resp.status_code != 200:
                print(f"❌ Meta Upload Error: {upload_resp.text}")
                return None
                
            # Return the required cryptographic handle!
            return upload_resp.json().get("h")
            
    except Exception as e:
        print(f"❌ Dummy Media Handle Error: {str(e)}")
        return None

# 🚀 UPDATED CREATE FUNCTION
async def create_template_in_meta(
    waba_id: str, 
    access_token: str, 
    name: str, 
    category: str, 
    language: str, 
    body_text: str,
    header_type: str = "NONE",
    header_text: str | None = None,
    buttons: list[dict] | None = None,
) -> dict | None:
    url = f"{GRAPH_BASE}/{waba_id}/message_templates"
    
    var_matches = re.findall(r'\{\{(\d+)\}\}', body_text)
    var_count = max([int(num) for num in var_matches]) if var_matches else 0
    
    components = [{"type": "BODY", "text": body_text}]
    if var_count > 0:
        components[0]["example"] = {"body_text": [["Sample"] * var_count]}

    # 🚀 FIXED HEADER LOGIC: Use the Resumable Upload Helper!
    if header_type in ["IMAGE", "VIDEO", "DOCUMENT"]:
        print(f"⏳ Generating secure dummy media handle for {header_type}...")
        handle = await get_dummy_media_handle(access_token, header_type)
        
        if handle:
            components.append({
                "type": "HEADER",
                "format": header_type,
                "example": {"header_handle": [handle]} # 🚀 Successfully passing the ID!
            })
        else:
            print("⚠️ Could not generate media handle. Meta will likely reject this request.")
            
    elif header_type == "TEXT" and header_text:
        components.append({
            "type": "HEADER",
            "format": "TEXT",
            "text": header_text
        })

        # 🚀 NEW: BUTTONS component
    if buttons:
        # Enforce Meta's rules: max 3 QUICK_REPLY, max 2 URL, max 1 PHONE_NUMBER
        quick_reply = [b for b in buttons if b["type"] == "QUICK_REPLY"][:3]
        url_buttons = [b for b in buttons if b["type"] == "URL"][:2]
        phone_buttons = [b for b in buttons if b["type"] == "PHONE_NUMBER"][:1]

        button_objs = []
        for b in quick_reply:
            button_objs.append({"type": "QUICK_REPLY", "text": b["text"]})
        for b in url_buttons:
            btn = {"type": "URL", "text": b["text"], "url": b["url"]}
            if "{{1}}" in b["url"]:
                btn["example"] = [b["url"].replace("{{1}}", "sample-value")]
            button_objs.append(btn)
        for b in phone_buttons:
            button_objs.append({
                "type": "PHONE_NUMBER", "text": b["text"], "phone_number": b["phone_number"]
            })

        if button_objs:
            components.append({"type": "BUTTONS", "buttons": button_objs})    

    payload = {
        "name": name,
        "category": category,
        "language": language,
        "components": components
    }
    
    try:
        # Increased timeout to 45 seconds because we are doing multiple network requests now!
        async with httpx.AsyncClient(timeout=45.0) as client: 
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

# 🚀 UPDATED: Now supports sending with a Media ID instead of a URL
async def send_template_message(
    phone_number_id: str,
    access_token: str, 
    to_phone: str, 
    template_name: str, 
    language_code: str, 
    body_params: list[str], 
    header_type: str = "NONE", 
    media_url: str = None,
    media_id: str = None, # 🚀 ADDED THIS
    button_url_param: str = None,
) -> bool:
    
    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    
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
    
    if header_type in ["IMAGE", "VIDEO", "DOCUMENT"]:
        param_type = header_type.lower()
        header_param = {"type": param_type}
        
        # Prefer the direct ID if we have it, otherwise fallback to URL
        if media_id:
            header_param[param_type] = {"id": media_id}
        elif media_url:
            header_param[param_type] = {"link": media_url}
            
        if media_id or media_url:
            payload["template"]["components"].append({
                "type": "header",
                "parameters": [header_param]
            })
        
    if body_params:
        body_parameters = [{"type": "text", "text": str(param)} for param in body_params]
        payload["template"]["components"].append({
            "type": "body",
            "parameters": body_parameters
        })
    # 🚀 ADD THIS EXACT LINE:

    if button_url_param:
        payload["template"]["components"].append({
            "type": "button",
            "sub_type": "url",
            "index": "0",
            "parameters": [{"type": "text", "text": button_url_param}]
        })

    print(f"\n🚀 META PAYLOAD: {payload}\n")    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, headers={"Authorization": f"Bearer {access_token}"}, json=payload)
            if response.status_code in [200, 201]:
               
                # 🚀 Return the actual wamid string!
                return response.json().get("messages", [{}])[0].get("id")
            else:
                print(f"❌ SEND FAILED: {response.text}")
                return False
    except Exception as e:
        print(f"❌ SEND CRASHED: {str(e)}")
        return False
        
# 🚀 NEW: Securely upload a real file to Meta for sending campaigns
async def upload_media_to_meta(phone_number_id: str, access_token: str, file_bytes: bytes, file_name: str, mime_type: str) -> str | None:
    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/media"
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            data = {"messaging_product": "whatsapp"}
            files = {"file": (file_name, file_bytes, mime_type)}
            
            response = await client.post(
                url, 
                headers={"Authorization": f"Bearer {access_token}"},
                data=data,
                files=files
            )
            
            if response.status_code == 200:
                return response.json().get("id") # Returns the secure Meta Media ID!
            else:
                print(f"❌ Media Upload Failed: {response.text}")
                return None
    except Exception as e:
        print(f"❌ Media Upload Crashed: {str(e)}")
        return None        