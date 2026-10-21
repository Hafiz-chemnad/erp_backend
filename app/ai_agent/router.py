from fastapi import APIRouter, HTTPException
from app.db import get_database
from app.ai_agent.schemas import (
    AiAgentStatusOut, PromptConfigIn, PromptConfigOut,
    PlaceOrderIn, PlaceOrderOut, ChatTurnIn, ChatTurnOut,
)
from app.ai_agent import service
from app.ai_agent.service import AgentBackendError

router = APIRouter(prefix="/api/{restaurant_id}/ai-agent", tags=["AI Agent"])


@router.get("/status", response_model=AiAgentStatusOut)
async def status(restaurant_id: str):
    db = get_database()
    try:
        return await service.get_status(db, restaurant_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/enable", response_model=AiAgentStatusOut)
async def enable(restaurant_id: str):
    db = get_database()
    try:
        await service.enable_ai_agent(db, restaurant_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except AgentBackendError as e:
        raise HTTPException(502, str(e))
    return await service.get_status(db, restaurant_id)


@router.post("/disable", response_model=AiAgentStatusOut)
async def disable(restaurant_id: str):
    db = get_database()
    try:
        await service.disable_ai_agent(db, restaurant_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return await service.get_status(db, restaurant_id)


@router.get("/prompt-config", response_model=PromptConfigOut)
async def get_prompt_config(restaurant_id: str):
    db = get_database()
    try:
        config = await service.get_prompt_config(db, restaurant_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return config or PromptConfigOut()


@router.put("/prompt-config", response_model=PromptConfigOut)
async def save_prompt_config(restaurant_id: str, body: PromptConfigIn):
    db = get_database()
    try:
        await service.save_prompt_config(db, restaurant_id, body)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except AgentBackendError as e:
        raise HTTPException(502, str(e))
    return body


@router.post("/place-order", response_model=PlaceOrderOut)
async def place_order(restaurant_id: str, body: PlaceOrderIn):
    """Called by agent-backend's place_order Tool — not by the Flutter app."""
    db = get_database()
    try:
        return await service.place_ai_order(db, restaurant_id, body)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/chat", response_model=ChatTurnOut)
async def chat(restaurant_id: str, body: ChatTurnIn):
    """Used by webhooks/router.py to proxy a WhatsApp message to the AI, and
    can also be called directly for a dashboard test-chat widget later."""
    db = get_database()
    try:
        return await service.send_chat_turn(db, restaurant_id, body.transcript, body.sessionState)
    except AgentBackendError as e:
        raise HTTPException(502, str(e))
