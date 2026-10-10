import httpx
from app.core.config import settings

# Free-tier-first LLM routing: Groq is tried first (fast, generous free
# tier), Gemini Flash is the fallback. Both are optional — if neither
# key is configured, callers get None back and fall back to template-based
# copy instead of failing outright.

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_GROQ_MODEL = "llama-3.1-8b-instant"

_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"


async def _ask_groq(system_prompt: str, user_message: str) -> str | None:
    if not settings.GROQ_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _GROQ_URL,
                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                json={
                    "model": _GROQ_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 400,
                },
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        pass
    return None


async def _ask_gemini(system_prompt: str, user_message: str) -> str | None:
    if not settings.GEMINI_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{_GEMINI_URL}?key={settings.GEMINI_API_KEY}",
                json={
                    "contents": [{"parts": [{"text": f"{system_prompt}\n\n{user_message}"}]}],
                    "generationConfig": {"temperature": 0.3, "maxOutputTokens": 400},
                },
            )
            if resp.status_code == 200:
                return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        pass
    return None


async def ask_llm(system_prompt: str, user_message: str) -> str | None:
    """Tries Groq, then Gemini. Returns None if both are unavailable/unconfigured
    — callers must handle that gracefully (template fallback), never crash."""
    answer = await _ask_groq(system_prompt, user_message)
    if answer:
        return answer
    return await _ask_gemini(system_prompt, user_message)
