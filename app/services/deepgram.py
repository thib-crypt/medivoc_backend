import httpx
from app.config import settings

DEEPGRAM_TRANSCRIPTION_URL = "https://api.deepgram.com/v1/listen"
DEEPGRAM_MODEL = "nova-3"


async def transcribe(audio_bytes: bytes, mimetype: str = "audio/wav") -> str:
    params = {
        "model": DEEPGRAM_MODEL,
        "smart_format": "true",
        "punctuate": "true",
        "language": "fr",
    }
    headers = {
        "Authorization": f"Token {settings.deepgram_api_key}",
        "Content-Type": mimetype,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            DEEPGRAM_TRANSCRIPTION_URL,
            headers=headers,
            params=params,
            content=audio_bytes,
        )
        response.raise_for_status()
        data = response.json()

    try:
        transcript = data["results"]["channels"][0]["alternatives"][0]["transcript"]
    except (KeyError, IndexError):
        transcript = ""

    return transcript.strip()
