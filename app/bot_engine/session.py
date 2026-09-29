"""Thin wrapper around app.core.redis session helpers, matching Node's
customersessions shape: {flowName, stepIndex, data}."""

from app.core import redis as redis_core


async def load(phone_number_id: str, customer_number: str) -> dict:
    session = await redis_core.get_session(phone_number_id, customer_number)
    if not session:
        # "fresh" = first contact (nothing stored in Redis yet). The engine uses it
        # to SEND the first step (welcome) instead of treating the customer's
        # first message as an answer to a question they haven't been asked.
        session = {"flowName": "default_flow", "stepIndex": 0, "data": {}, "fresh": True}
    return session


async def save(phone_number_id: str, customer_number: str, session: dict):
    await redis_core.save_session(phone_number_id, customer_number, session)


async def clear(phone_number_id: str, customer_number: str):
    await redis_core.clear_session(phone_number_id, customer_number)