import httpx
from typing import AsyncGenerator
from app.config import settings

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-2.0-flash"


def _build_payload(text: str, instructions: str, model: str) -> dict:
    system_instruction = instructions if instructions else "Tu es un assistant médical expert."
    return {
        "system_instruction": {"parts": [{"text": system_instruction}]},
        "contents": [{"role": "user", "parts": [{"text": text}]}],
        "generationConfig": {"temperature": 0.3},
    }


async def process_text(text: str, instructions: str = "", model: str = DEFAULT_MODEL) -> str:
    url = f"{GEMINI_BASE_URL}/{model}:generateContent"
    params = {"key": settings.gemini_api_key}
    payload = _build_payload(text, instructions, model)

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=payload, params=params)
        response.raise_for_status()
        data = response.json()

    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError):
        return ""


async def stream_text(
    text: str, instructions: str = "", model: str = DEFAULT_MODEL
) -> AsyncGenerator[str, None]:
    url = f"{GEMINI_BASE_URL}/{model}:streamGenerateContent"
    params = {"key": settings.gemini_api_key, "alt": "sse"}
    payload = _build_payload(text, instructions, model)

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", url, json=payload, params=params) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[len("data:"):].strip()
                if not raw or raw == "[DONE]":
                    continue
                import json
                try:
                    chunk_data = json.loads(raw)
                    chunk_text = chunk_data["candidates"][0]["content"]["parts"][0]["text"]
                    if chunk_text:
                        yield chunk_text
                except (KeyError, IndexError, json.JSONDecodeError):
                    continue
