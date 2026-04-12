from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models import Card, Deck
from app.config import settings

router = APIRouter(tags=["chat"])

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    reply: str

@router.post("/chat/deck/{deck_id}", response_model=ChatResponse)
def deck_chat(
    deck_id: str,
    payload: ChatRequest,
    db: Session = Depends(get_db),
    x_groq_api_key: str | None = Header(default=None, alias="X-Groq-Api-Key")
) -> ChatResponse:
    resolved_key = x_groq_api_key or settings.groq_api_key
    if not resolved_key:
        raise HTTPException(status_code=400, detail="Groq API key not configured")

    deck = db.get(Deck, deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")

    stmt = select(Card.front, Card.back).where(Card.deck_id == deck_id).limit(100)
    cards = db.execute(stmt).all()
    
    context_lines = [f"Q: {c.front}\nA: {c.back}" for c in cards]
    context_str = "\n\n".join(context_lines)

    try:
        from groq import Groq
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="groq package not installed")

    client = Groq(api_key=resolved_key)

    sys_prompt = (
        f"You are a helpful study tutor answering questions strictly based on the provided flashcard deck '{deck.name}'.\n"
        "Here are up to 100 flashcards from the deck:\n"
        f"---\n{context_str}\n---\n"
        "Answer the user's question clearly. If the answer isn't in the deck, you can say so but provide helpful general knowledge if relevant."
    )

    try:
        response = client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": payload.message}
            ],
            temperature=0.7,
        )
        return ChatResponse(reply=response.choices[0].message.content.strip())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Groq API chat failed: {exc}")
