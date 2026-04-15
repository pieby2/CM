from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Card, Deck
from app.services.ai_client import AIClientError, generate_completion

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
    x_ai_api_key: str | None = Header(default=None, alias="X-AI-Api-Key"),
    x_ai_provider: str | None = Header(default=None, alias="X-AI-Provider"),
    x_groq_api_key: str | None = Header(default=None, alias="X-Groq-Api-Key"),
) -> ChatResponse:
    deck = db.get(Deck, deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")

    stmt = select(Card.front, Card.back).where(Card.deck_id == deck_id).limit(100)
    cards = db.execute(stmt).all()

    context_lines = [f"Q: {card.front}\nA: {card.back}" for card in cards]
    context_str = "\n\n".join(context_lines)

    sys_prompt = (
        f"You are a helpful study tutor answering questions strictly based on the provided flashcard deck '{deck.name}'.\n"
        "Here are up to 100 flashcards from the deck:\n"
        f"---\n{context_str}\n---\n"
        "Answer the user's question clearly. If the answer isn't in the deck, you can say so but provide helpful general knowledge if relevant."
    )

    try:
        reply = generate_completion(
            system_prompt=sys_prompt,
            user_prompt=payload.message,
            api_key=x_ai_api_key or x_groq_api_key,
            provider=x_ai_provider,
            temperature=0.7,
        )
        return ChatResponse(reply=reply)
    except AIClientError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
