import httpx
from app.core.config import settings

# Free-tier voice-note transcription via Groq's Whisper endpoint — same
# GROQ_API_KEY already used by Insights' llm_client.py, no new dependency or
# cost. agent-backend's own Whisper client is built for its real-time phone
# pipeline (pipecat streaming), which isn't used here — a plain one-shot
# REST call is simpler and all a WhatsApp voice note needs.

_GROQ_TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
_GROQ_MODEL = "whisper-large-v3-turbo"


async def transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str | None:
    """Returns the transcript, or None if transcription is unavailable/fails
    — callers must handle that gracefully (ask the customer to type instead),
    never crash the webhook over a bad or unsupported voice note."""
    if not settings.GROQ_API_KEY:
        return None

    filename = "voice_note.ogg" if "ogg" in mime_type else "voice_note.m4a"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                _GROQ_TRANSCRIBE_URL,
                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                data={"model": _GROQ_MODEL},
                files={"file": (filename, audio_bytes, mime_type)},
            )
            if resp.status_code == 200:
                text = resp.json().get("text", "").strip()
                return text or None
            print("GROQ STT ERROR:", resp.status_code, resp.text[:300])
    except Exception as e:
        print("GROQ STT EXCEPTION:", e)
    return None
