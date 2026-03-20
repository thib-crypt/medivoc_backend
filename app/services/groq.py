import httpx
from app.config import settings

GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODEL = "whisper-large-v3"


async def transcribe(audio_bytes: bytes, filename: str = "audio.wav") -> str:
    async with httpx.AsyncClient(timeout=120.0) as client:
        files = {"file": (filename, audio_bytes, "audio/wav")}
        data = {"model": GROQ_MODEL, "response_format": "text"}
        headers = {"Authorization": f"Bearer {settings.groq_api_key}"}

        response = await client.post(
            GROQ_TRANSCRIPTION_URL,
            headers=headers,
            files=files,
            data=data,
        )
        response.raise_for_status()
        return response.text.strip()
