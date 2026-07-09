import logging
import re
from datetime import datetime, timezone
from app.templates import meta_client
from app.templates.schemas import TemplateCreateIn, TemplateOut, TemplateListResponse

logger = logging.getLogger(__name__)
COLLECTION = "templates"

def _extract_template_data(components: list) -> tuple[str, int, str, str | None]:
    body_text = ""
    var_count = 0
    header_type = "NONE"
    header_text = None
    
    for comp in components:
        if comp.get("type") == "BODY":
            body_text = comp.get("text", "")
            var_count = len(re.findall(r'\{\{\d+\}\}', body_text))
        elif comp.get("type") == "HEADER":
            header_type = comp.get("format", "NONE")
            if header_type == "TEXT":
                header_text = comp.get("text")
                
    return body_text, var_count, header_type, header_text

async def list_templates(db, restaurant_id: str) -> TemplateListResponse:
    coll = db[COLLECTION]
    cursor = coll.find({"restaurant_id": restaurant_id}).sort([("created_at", -1)])
    docs = await cursor.to_list(length=500)
    items = [TemplateOut(**doc) for doc in docs]
    return TemplateListResponse(items=items)

# app/templates/service.py

async def create_template(db, restaurant_id: str, body: TemplateCreateIn) -> TemplateOut | str:
    # 🚀 Update method call to handle new arguments
    meta_response = await meta_client.create_template_in_meta(
        waba_id=body.waba_id,
        access_token=body.access_token,
        name=body.name,
        category=body.category,
        language=body.language,
        body_text=body.body_text,
        header_type=body.header_type,   # 🚀 ADDED
        header_text=body.header_text    # 🚀 ADDED
    )
    
    if not meta_response:
        return "meta_error"

    coll = db[COLLECTION]
    now = datetime.now(timezone.utc)
    var_count = len(re.findall(r'\{\{\d+\}\}', body.body_text))
    template_id = meta_response.get("id", f"temp_{int(now.timestamp() * 1000)}")

    doc = {
        "template_id": template_id,
        "restaurant_id": restaurant_id,
        "name": body.name,
        "category": body.category,
        "language": body.language,
        "body_text": body.body_text,
        "variable_count": var_count,
        "status": "PENDING",
        "rejected_reason": None,
        "default_mappings": {},
        "created_at": now,
        # 🚀 ADD TO MONGO SYSTEM TRACKING
        "header_type": body.header_type,
        "header_text": body.header_text
    }
    
    await coll.update_one(
        {"restaurant_id": restaurant_id, "name": body.name},
        {"$set": doc},
        upsert=True
    )
    return TemplateOut(**doc)

async def refresh_template_statuses(db, restaurant_id: str, waba_id: str, access_token: str) -> TemplateListResponse:
    """Fetches latest statuses from Meta and syncs them to Mongo."""
    from app.templates import meta_client
    
    meta_templates = await meta_client.fetch_templates_from_meta(waba_id, access_token)
    coll = db[COLLECTION]
    
    for tmpl in meta_templates:
        # 🚀 Use the new extractor
        body_text, var_count, header_type, header_text = _extract_template_data(tmpl.get("components", []))
        
        update_doc = {
            "template_id": tmpl.get("id", ""),
            "status": tmpl.get("status", "PENDING"),
            "rejected_reason": tmpl.get("rejected_reason"),
            "category": tmpl.get("category"),
            "language": tmpl.get("language"),
            "body_text": body_text,
            "variable_count": var_count,
            "header_type": header_type, # 🚀 ADDED
            "header_text": header_text, # 🚀 ADDED
            "updated_at": datetime.now(timezone.utc)
        }
        
        # 🚀 FIX: Use $setOnInsert to provide defaults for brand new templates
        await coll.update_one(
            {"restaurant_id": restaurant_id, "name": tmpl.get("name")},
            {
                "$set": update_doc,
                "$setOnInsert": {
                    "default_mappings": {},
                    "created_at": datetime.now(timezone.utc)
                }
            },
            upsert=True
        )
        
    return await list_templates(db, restaurant_id)

async def delete_template(db, restaurant_id: str, name: str, waba_id: str, access_token: str) -> str:
    coll = db[COLLECTION]
    success = await meta_client.delete_template_in_meta(waba_id, access_token, name)
    
    if success:
        await coll.delete_one({"restaurant_id": restaurant_id, "name": name})
        return "ok"
    return "error"