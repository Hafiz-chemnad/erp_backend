import logging
import re
from datetime import datetime, timezone
from app.templates import meta_client
from app.templates.schemas import TemplateCreateIn, TemplateOut, TemplateListResponse

logger = logging.getLogger(__name__)
COLLECTION = "templates"


def _extract_template_data(components: list) -> tuple[str, int, str, str | None, list | None]:
    body_text = ""
    var_count = 0
    header_type = "NONE"
    header_text = None
    buttons = None

    for comp in components:
        if comp.get("type") == "BODY":
            body_text = comp.get("text", "")
            var_count = len(re.findall(r'\{\{\d+\}\}', body_text))
        elif comp.get("type") == "HEADER":
            header_type = comp.get("format", "NONE")
            if header_type == "TEXT":
                header_text = comp.get("text")
        elif comp.get("type") == "BUTTONS":
            buttons = comp.get("buttons", [])

    return body_text, var_count, header_type, header_text, buttons


def validate_sequential_variables(body_text: str) -> str | None:
    """🚀 NEW: catches {{1}}, {{3}} (missing {{2}}) BEFORE hitting Meta.
    Without this, a gap silently produces a mismatched example array in
    create_template_in_meta and Meta rejects with a generic error that
    doesn't tell the user what's actually wrong. Returns an error message
    string if invalid, or None if the body text is fine."""
    positions = sorted(int(m) for m in re.findall(r'\{\{(\d+)\}\}', body_text))
    if not positions:
        return None
    expected = list(range(1, len(positions) + 1))
    if positions != expected:
        return f"Variables must be sequential starting at {{{{1}}}} with no gaps. Found: {positions}, expected: {expected}"
    if len(positions) > 15:
        return "Maximum of 15 variables allowed"
    return None


async def list_templates(db, restaurant_id: str) -> TemplateListResponse:
    coll = db[COLLECTION]
    cursor = coll.find({"restaurant_id": restaurant_id}).sort([("created_at", -1)])
    docs = await cursor.to_list(length=500)
    items = [TemplateOut(**doc) for doc in docs]
    return TemplateListResponse(items=items)


async def create_template(db, restaurant_id: str, body: TemplateCreateIn) -> TemplateOut | str:
    # 🚀 NEW: validate before ever calling Meta.
    validation_error = validate_sequential_variables(body.body_text)
    if validation_error:
        return f"validation_error:{validation_error}"

    meta_response = await meta_client.create_template_in_meta(
        waba_id=body.waba_id,
        access_token=body.access_token,
        name=body.name,
        category=body.category,
        language=body.language,
        body_text=body.body_text,
        header_type=body.header_type,
        header_text=body.header_text,
        buttons=[b.dict() for b in body.buttons] if body.buttons else None,
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
        "header_type": body.header_type,
        "header_text": body.header_text,
        "buttons": [b.dict() for b in body.buttons] if body.buttons else None,
    }

    await coll.update_one({"restaurant_id": restaurant_id, "name": body.name}, {"$set": doc}, upsert=True)
    return TemplateOut(**doc)


async def refresh_template_statuses(db, restaurant_id: str, waba_id: str, access_token: str) -> TemplateListResponse:
    from app.templates import meta_client

    meta_templates = await meta_client.fetch_templates_from_meta(waba_id, access_token)
    coll = db[COLLECTION]

    for tmpl in meta_templates:
        body_text, var_count, header_type, header_text, buttons = _extract_template_data(tmpl.get("components", []))

        update_doc = {
            "template_id": tmpl.get("id", ""),
            "status": tmpl.get("status", "PENDING"),
            "rejected_reason": tmpl.get("rejected_reason"),
            "category": tmpl.get("category"),
            "language": tmpl.get("language"),
            "body_text": body_text,
            "variable_count": var_count,
            "header_type": header_type,
            "header_text": header_text,
            "buttons": buttons,
            "updated_at": datetime.now(timezone.utc)
        }

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


async def update_variable_mapping(db, restaurant_id: str, name: str, mapping: dict) -> str:
    """🚀 NEW: actually persists the owner's blank->source choices to
    Mongo, keyed by template name. Without this, mapping choices only
    ever lived in local SQLite and were lost on reinstall/new device."""
    coll = db[COLLECTION]
    existing = await coll.find_one({"restaurant_id": restaurant_id, "name": name})
    if existing is None:
        return "not_found"

    await coll.update_one(
        {"restaurant_id": restaurant_id, "name": name},
        {"$set": {"default_mappings": mapping}},
    )
    return "ok"