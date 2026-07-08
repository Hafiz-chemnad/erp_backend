import logging
import re
from datetime import datetime, timezone
from app.templates import meta_client
from app.templates.schemas import TemplateCreateIn, TemplateOut, TemplateListResponse

logger = logging.getLogger(__name__)
COLLECTION = "templates"

def _extract_body_text_and_vars(components: list) -> tuple[str, int]:
    for comp in components:
        if comp.get("type") == "BODY":
            text = comp.get("text", "")
            var_count = len(re.findall(r'\{\{\d+\}\}', text))
            return text, var_count
    return "", 0

async def list_templates(db, restaurant_id: str) -> TemplateListResponse:
    coll = db[COLLECTION]
    cursor = coll.find({"restaurant_id": restaurant_id}).sort([("created_at", -1)])
    docs = await cursor.to_list(length=500)
    items = [TemplateOut(**doc) for doc in docs]
    return TemplateListResponse(items=items)

async def create_template(db, restaurant_id: str, body: TemplateCreateIn) -> TemplateOut | str:
    meta_response = await meta_client.create_template_in_meta(
        waba_id=body.waba_id,
        access_token=body.access_token,
        name=body.name,
        category=body.category,
        language=body.language,
        body_text=body.body_text
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
        "status": "PENDING", # Always starts pending
        "rejected_reason": None,
        "default_mappings": {},
        "created_at": now,
    }
    
    await coll.update_one(
        {"restaurant_id": restaurant_id, "name": body.name},
        {"$set": doc},
        upsert=True
    )
    return TemplateOut(**doc)

async def refresh_template_statuses(db, restaurant_id: str, waba_id: str, access_token: str) -> TemplateListResponse:
    """Fetches latest statuses from Meta and syncs them to Mongo."""
    meta_templates = await meta_client.fetch_templates_from_meta(waba_id, access_token)
    coll = db[COLLECTION]
    
    for tmpl in meta_templates:
        body_text, var_count = _extract_body_text_and_vars(tmpl.get("components", []))
        
        update_doc = {
            "status": tmpl.get("status", "PENDING"),
            "rejected_reason": tmpl.get("rejected_reason"),
            "category": tmpl.get("category"),
            "language": tmpl.get("language"),
            "body_text": body_text,
            "variable_count": var_count,
            "updated_at": datetime.now(timezone.utc)
        }
        
        await coll.update_one(
            {"restaurant_id": restaurant_id, "name": tmpl.get("name")},
            {"$set": update_doc},
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