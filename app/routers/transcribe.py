from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException
from app.dependencies import check_transcription_quota
from app.services.supabase_client import get_supabase

router = APIRouter(prefix="/api/v1", tags=["transcription"])

SUPPORTED_PROVIDERS = ("groq", "deepgram")


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    provider: str = Form("groq"),
    profile=Depends(check_transcription_quota),
):
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Fournisseur invalide. Valeurs acceptées : {', '.join(SUPPORTED_PROVIDERS)}",
        )

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Le fichier audio est vide.")

    duration_seconds = _estimate_duration(audio_bytes, file.filename or "audio.wav")

    try:
        if provider == "groq":
            from app.services.groq import transcribe
            text = await transcribe(audio_bytes, file.filename or "audio.wav")
        else:
            from app.services.deepgram import transcribe
            mimetype = file.content_type or "audio/wav"
            text = await transcribe(audio_bytes, mimetype)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Erreur du service de transcription ({provider}) : {str(e)}",
        )

    supabase = get_supabase()
    user_id = profile["id"]

    minutes_used = profile.get("minutes_used_this_month", 0)
    new_minutes = minutes_used + (duration_seconds / 60)
    supabase.table("profiles").update(
        {"minutes_used_this_month": new_minutes}
    ).eq("id", user_id).execute()

    supabase.table("usage_logs").insert({
        "user_id": user_id,
        "type": "transcription",
        "provider": provider,
        "duration_seconds": duration_seconds,
    }).execute()

    return {
        "text": text,
        "provider": provider,
        "duration_seconds": round(duration_seconds, 2),
    }


def _estimate_duration(audio_bytes: bytes, filename: str) -> float:
    try:
        import io
        from mutagen import File as MutagenFile
        audio = MutagenFile(io.BytesIO(audio_bytes))
        if audio and audio.info:
            return float(audio.info.length)
    except Exception:
        pass
    return max(1.0, len(audio_bytes) / 16000)
