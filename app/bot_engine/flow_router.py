from fastapi import APIRouter, HTTPException
from bson import ObjectId
from app.db import get_database
from app.bot_engine.flow_schema import Flow, get_flow, get_default_flow

router = APIRouter(prefix="/api/{restaurant_id}/bot-flow", tags=["Bot Flow"])


@router.get("", response_model=Flow)
async def fetch_flow(restaurant_id: str, flow_name: str = "default_flow"):
    """Returns the restaurant's saved flow, or the built-in default flow
    (pre-filled, fully editable) if they've never customized one — the
    Flow Builder always has something real to show, never a blank screen."""
    db = get_database()
    restaurant = await db.restaurants.find_one({"_id": ObjectId(restaurant_id)})
    if not restaurant:
        raise HTTPException(404, "Restaurant not found")
    return get_flow(restaurant, flow_name)


@router.put("", response_model=Flow)
async def save_flow(restaurant_id: str, body: Flow):
    """Upserts this named flow into restaurant.flows — same field the bot
    engine already reads via get_flow(), so saving here takes effect on
    the very next WhatsApp message, no redeploy needed."""
    db = get_database()
    restaurant = await db.restaurants.find_one({"_id": ObjectId(restaurant_id)})
    if not restaurant:
        raise HTTPException(404, "Restaurant not found")

    flows = restaurant.get("flows", [])
    flows = [f for f in flows if f.get("flowName") != body.flowName]
    flows.append(body.model_dump())

    await db.restaurants.update_one(
        {"_id": ObjectId(restaurant_id)},
        {"$set": {"flows": flows}},
    )
    return body


@router.post("/reset", response_model=Flow)
async def reset_flow(restaurant_id: str, flow_name: str = "default_flow"):
    """Discards any customization and restores the built-in default flow
    for this flow name — an escape hatch if an owner's edits break something."""
    db = get_database()
    restaurant = await db.restaurants.find_one({"_id": ObjectId(restaurant_id)})
    if not restaurant:
        raise HTTPException(404, "Restaurant not found")

    default = get_default_flow(flow_name)
    flows = restaurant.get("flows", [])
    flows = [f for f in flows if f.get("flowName") != flow_name]
    flows.append(default.model_dump())

    await db.restaurants.update_one(
        {"_id": ObjectId(restaurant_id)},
        {"$set": {"flows": flows}},
    )
    return default
