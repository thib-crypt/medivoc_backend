import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, WebSocketException, status

from app.dependencies import get_current_user_from_token, get_profile_by_user_id, check_quota_from_profile
from app.services.deepgram_streaming import stream_transcription
from app.services.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["dictation"])


@router.websocket("/dictate")
async def dictate_websocket(
    websocket: WebSocket,
    token: str = Query(..., description="JWT Supabase token"),
    language: str = Query("fr", description="Langue de transcription (ex: fr, en-US)"),
    interim_results: bool = Query(True, description="Renvoyer les résultats intermédiaires"),
):
    """
    WebSocket pour la dictée vocale en temps réel via Deepgram.

    Protocole :
    - Connexion : ws://.../api/v1/dictate?token=<jwt>&language=fr
    - Client → Serveur : chunks audio binaires (PCM 16-bit mono, 16kHz)
    - Serveur → Client : messages JSON :
        {"type": "transcript", "is_final": true, "speech_final": bool, "text": "...", "confidence": 0.99}
        {"type": "utterance_end"}
        {"type": "error", "message": "..."}
        {"type": "session_end", "total_seconds": 12.5}
    - Pour terminer : envoyer un message texte JSON {"action": "stop"}
    """
    await websocket.accept()

    # Auth
    try:
        user = await get_current_user_from_token(token)
    except Exception:
        await websocket.send_json({"type": "error", "message": "Token invalide ou expiré."})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Profil + quota
    try:
        profile = await get_profile_by_user_id(str(user.id))
        check_quota_from_profile(profile)
    except Exception as exc:
        await websocket.send_json({"type": "error", "message": str(exc)})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.send_json({"type": "connected", "message": "Session de dictée démarrée."})

    stop_event = asyncio.Event()
    audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
    total_bytes_received: int = 0

    async def receive_audio():
        nonlocal total_bytes_received
        try:
            while not stop_event.is_set():
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    break
                if message["type"] == "websocket.receive":
                    if "bytes" in message and message["bytes"]:
                        chunk = message["bytes"]
                        total_bytes_received += len(chunk)
                        await audio_queue.put(chunk)
                    elif "text" in message and message["text"]:
                        try:
                            data = json.loads(message["text"])
                            if data.get("action") == "stop":
                                break
                        except json.JSONDecodeError:
                            pass
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            logger.warning("WebSocket receive error: %s", exc)
        finally:
            stop_event.set()
            await audio_queue.put(b"")

    async def audio_generator() -> AsyncGenerator[bytes, None]:
        while True:
            chunk = await audio_queue.get()
            if not chunk:
                break
            if stop_event.is_set() and audio_queue.empty():
                break
            yield chunk

    receive_task = asyncio.create_task(receive_audio())

    session_start = asyncio.get_event_loop().time()

    try:
        async for event in stream_transcription(
            audio_generator(),
            language=language,
            interim_results=interim_results,
        ):
            if not stop_event.is_set() or event.get("type") in ("transcript", "utterance_end"):
                try:
                    await websocket.send_json(event)
                except Exception:
                    break
    except Exception as exc:
        logger.error("Streaming error: %s", exc)
        try:
            await websocket.send_json({"type": "error", "message": f"Erreur streaming : {exc}"})
        except Exception:
            pass
    finally:
        stop_event.set()
        receive_task.cancel()
        try:
            await receive_task
        except asyncio.CancelledError:
            pass

    total_seconds = asyncio.get_event_loop().time() - session_start

    try:
        await websocket.send_json({
            "type": "session_end",
            "total_seconds": round(total_seconds, 2),
        })
    except Exception:
        pass

    _log_usage(profile, total_seconds)

    try:
        await websocket.close()
    except Exception:
        pass


def _log_usage(profile: dict, duration_seconds: float):
    try:
        supabase = get_supabase()
        user_id = profile["id"]

        minutes_used = profile.get("minutes_used_this_month", 0)
        new_minutes = minutes_used + (duration_seconds / 60)
        supabase.table("profiles").update(
            {"minutes_used_this_month": new_minutes}
        ).eq("id", user_id).execute()

        supabase.table("usage_logs").insert({
            "user_id": user_id,
            "type": "dictation",
            "provider": "deepgram",
            "duration_seconds": round(duration_seconds, 2),
        }).execute()
    except Exception as exc:
        logger.error("Failed to log dictation usage: %s", exc)
