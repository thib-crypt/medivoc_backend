from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, transcribe, process_text, billing, dictate

app = FastAPI(
    title="Medivoc API",
    description="Backend sécurisé pour la transcription médicale et le traitement LLM.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(transcribe.router)
app.include_router(process_text.router)
app.include_router(billing.router)
app.include_router(dictate.router)


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "service": "medivoc-api"}
