from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import cards, chat, concepts, decks, imports, reviews, users

app = FastAPI(
    title="Cue Math API",
    version="0.1.0",
    description="Flashcard API with SM-2/HLR fallback scheduling, concept graph support, and PDF extraction pipeline.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    Path(settings.storage_path).mkdir(parents=True, exist_ok=True)


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


app.include_router(users.router, prefix="/api")
app.include_router(decks.router, prefix="/api")
app.include_router(cards.router, prefix="/api")
app.include_router(reviews.router, prefix="/api")
app.include_router(imports.router, prefix="/api")
app.include_router(concepts.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
