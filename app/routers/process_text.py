import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.dependencies import get_profile
from app.services.supabase_client import get_supabase
from app.services.gemini import process_text, stream_text

router = APIRouter(prefix="/api/v1", tags=["llm"])

DEFAULT_MODEL = "gemini-3.0-flash"


class ProcessTextRequest(BaseModel):
    text: str
    instructions: str = ""
    model: str = DEFAULT_MODEL


@router.post("/process-text")
async def process_text_endpoint(
    request: ProcessTextRequest,
    profile=Depends(get_profile),
):
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Le texte ne peut pas être vide.")

    try:
        result = await process_text(request.text, request.instructions, request.model)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Erreur du service LLM : {str(e)}",
        )

    supabase = get_supabase()
    supabase.table("usage_logs").insert({
        "user_id": profile["id"],
        "type": "llm",
        "provider": "gemini",
    }).execute()

    return {"result": result}


@router.post("/process-text/stream")
async def stream_text_endpoint(
    request: ProcessTextRequest,
    profile=Depends(get_profile),
):
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Le texte ne peut pas être vide.")

    user_id = profile["id"]

    async def event_generator():
        supabase = get_supabase()
        try:
            async for chunk in stream_text(request.text, request.instructions, request.model):
                payload = json.dumps({"chunk": chunk}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
        except Exception as e:
            error_payload = json.dumps({"error": str(e)}, ensure_ascii=False)
            yield f"data: {error_payload}\n\n"
        finally:
            supabase.table("usage_logs").insert({
                "user_id": user_id,
                "type": "llm",
                "provider": "gemini",
            }).execute()
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
