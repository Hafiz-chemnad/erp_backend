"""
Redis client — used exclusively for bot session state.

Why Redis over MongoDB for sessions:
  • Sub-millisecond read/write on every webhook message hit
  • TTL auto-clears abandoned conversations (no cron needed)
  • Simple key/value — no need for a full document store here
"""

import json
import redis.asyncio as aioredis
from app.core.config import settings

_redis_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def close_redis() -> None:
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None


# ── Bot session helpers ────────────────────────────────────────────────
# Key format: bot_session:{phoneNumberId}:{customerNumber}

def _session_key(phone_number_id: str, customer_number: str) -> str:
    return f"bot_session:{phone_number_id}:{customer_number}"


async def get_session(phone_number_id: str, customer_number: str) -> dict:
    r = await get_redis()
    raw = await r.get(_session_key(phone_number_id, customer_number))
    if raw:
        return json.loads(raw)
    return {}


async def save_session(
    phone_number_id: str,
    customer_number: str,
    session: dict,
    ttl: int = settings.BOT_SESSION_TTL_SECONDS,
) -> None:
    r = await get_redis()
    await r.set(
        _session_key(phone_number_id, customer_number),
        json.dumps(session, default=str),
        ex=ttl,
    )


async def clear_session(phone_number_id: str, customer_number: str) -> None:
    r = await get_redis()
    await r.delete(_session_key(phone_number_id, customer_number))