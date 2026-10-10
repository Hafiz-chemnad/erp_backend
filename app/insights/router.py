from fastapi import APIRouter, HTTPException
from bson import ObjectId
from app.db import get_database
from app.insights.schemas import (
    AskQuestionIn, AskQuestionOut,
    AnalyticsSnapshotOut, ChurnCandidateOut, UpsellSuggestionOut,
    SendWinbackIn, SendWinbackOut,
)
from app.insights import service
from app.bot_engine.meta_sender import send_text

router = APIRouter(prefix="/api/{restaurant_id}/insights", tags=["Insights"])


@router.get("/analytics", response_model=AnalyticsSnapshotOut)
async def analytics(restaurant_id: str, days: int = 30):
    db = get_database()
    return await service.get_analytics_snapshot(db, restaurant_id, period_days=days)


@router.get("/churn-candidates", response_model=list[ChurnCandidateOut])
async def churn_candidates(restaurant_id: str, inactive_days: int = 14):
    db = get_database()
    return await service.get_churn_candidates(db, restaurant_id, inactive_days=inactive_days)


@router.get("/upsell-suggestions", response_model=list[UpsellSuggestionOut])
async def upsell_suggestions(restaurant_id: str):
    db = get_database()
    return await service.get_upsell_suggestions(db, restaurant_id)


@router.post("/ask", response_model=AskQuestionOut)
async def ask(restaurant_id: str, body: AskQuestionIn):
    db = get_database()
    if not body.question.strip():
        raise HTTPException(400, "Question cannot be empty")
    return await service.ask_question(db, restaurant_id, body.question)


@router.post("/send-winback", response_model=SendWinbackOut)
async def send_winback(restaurant_id: str, body: SendWinbackIn):
    db = get_database()
    if not body.customerNumbers:
        raise HTTPException(400, "No customers selected")

    restaurant = await db.restaurants.find_one({"_id": ObjectId(restaurant_id)})
    if not restaurant or not restaurant.get("waToken") or not restaurant.get("phoneNumberId"):
        raise HTTPException(400, "Restaurant's WhatsApp credentials aren't configured")

    sent, failed = 0, 0
    for number in body.customerNumbers:
        try:
            await send_text(restaurant["phoneNumberId"], number, body.message, restaurant["waToken"])
            sent += 1
        except Exception:
            failed += 1

    return {"sentCount": sent, "failedCount": failed}
