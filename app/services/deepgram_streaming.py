import asyncio
import logging
from typing import AsyncGenerator

from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveOptions,
    LiveTranscriptionEvents,
)

from app.config import settings

logger = logging.getLogger(__name__)

DEEPGRAM_MODEL = "nova-2"
SAMPLE_RATE = 16000


def _make_client() -> DeepgramClient:
    config = DeepgramClientOptions(options={"keepalive": "true"})
    return DeepgramClient(api_key=settings.deepgram_api_key, config=config)


def _make_live_options(language: str = "fr", interim_results: bool = True) -> LiveOptions:
    return LiveOptions(
        model=DEEPGRAM_MODEL,
        language=language,
        smart_format=True,
        punctuate=True,
        interim_results=interim_results,
        endpointing=300,
        utterance_end_ms="1000",
        encoding="linear16",
        sample_rate=SAMPLE_RATE,
        channels=1,
    )


async def stream_transcription(
    audio_chunks: AsyncGenerator[bytes, None],
    language: str = "fr",
    interim_results: bool = True,
) -> AsyncGenerator[dict, None]:
    """
    Receives audio chunks and yields transcription events as dicts:
      - {"type": "transcript", "is_final": bool, "text": str, "confidence": float}
      - {"type": "utterance_end"}
      - {"type": "error", "message": str}
    """
    client = _make_client()
    result_queue: asyncio.Queue[dict | None] = asyncio.Queue()

    dg_connection = client.listen.asyncwebsocket.v("1")

    async def on_transcript(self, result, **kwargs):
        try:
            channel = result.channel
            alt = channel.alternatives[0]
            text = alt.transcript
            if not text:
                return
            await result_queue.put({
                "type": "transcript",
                "is_final": result.is_final,
                "speech_final": getattr(result, "speech_final", False),
                "text": text,
                "confidence": round(alt.confidence, 4) if alt.confidence else None,
            })
        except Exception as exc:
            logger.warning("Error parsing Deepgram transcript: %s", exc)

    async def on_utterance_end(self, utterance_end, **kwargs):
        await result_queue.put({"type": "utterance_end"})

    async def on_error(self, error, **kwargs):
        logger.error("Deepgram live error: %s", error)
        await result_queue.put({"type": "error", "message": str(error)})

    async def on_close(self, close, **kwargs):
        await result_queue.put(None)

    dg_connection.on(LiveTranscriptionEvents.Transcript, on_transcript)
    dg_connection.on(LiveTranscriptionEvents.UtteranceEnd, on_utterance_end)
    dg_connection.on(LiveTranscriptionEvents.Error, on_error)
    dg_connection.on(LiveTranscriptionEvents.Close, on_close)

    options = _make_live_options(language=language, interim_results=interim_results)

    connected = await dg_connection.start(options)
    if not connected:
        yield {"type": "error", "message": "Impossible de se connecter à Deepgram."}
        return

    async def _send_audio():
        try:
            async for chunk in audio_chunks:
                if not chunk:
                    continue
                await dg_connection.send(chunk)
        except Exception as exc:
            logger.warning("Audio send interrupted: %s", exc)
        finally:
            await dg_connection.finish()

    send_task = asyncio.create_task(_send_audio())

    try:
        while True:
            event = await result_queue.get()
            if event is None:
                break
            yield event
    finally:
        send_task.cancel()
        try:
            await send_task
        except asyncio.CancelledError:
            pass
