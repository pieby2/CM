from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Card, CardState, Deck, utcnow
from app.schemas import CardCreate, CardRead, CardUpdate

router = APIRouter(tags=["cards"])


@router.post("/cards", response_model=CardRead, status_code=status.HTTP_201_CREATED)
def create_card(payload: CardCreate, db: Session = Depends(get_db)) -> Card:
    deck = db.get(Deck, payload.deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")

    card = Card(
        deck_id=payload.deck_id,
        section_id=payload.section_id,
        front=payload.front.strip(),
        back=payload.back.strip(),
        tags=payload.tags,
        type=payload.type,
        difficulty_estimate=payload.difficulty_estimate,
    )
    db.add(card)
    db.flush()

    state = CardState(
        user_id=deck.user_id,
        card_id=card.id,
        due_at=utcnow(),
        status="new",
        ease_factor=2.5,
        reps=0,
        interval_days=0,
    )
    db.add(state)

    db.commit()
    db.refresh(card)
    return card


@router.get("/cards", response_model=list[CardRead])
def list_cards(deck_id: str | None = Query(default=None), db: Session = Depends(get_db)) -> list[Card]:
    stmt = select(Card).order_by(Card.created_at.desc())
    if deck_id:
        stmt = stmt.where(Card.deck_id == deck_id)

    return list(db.scalars(stmt).all())


@router.get("/cards/{card_id}", response_model=CardRead)
def get_card(card_id: str, db: Session = Depends(get_db)) -> Card:
    card = db.get(Card, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return card


@router.put("/cards/{card_id}", response_model=CardRead)
def update_card(card_id: str, payload: CardUpdate, db: Session = Depends(get_db)) -> Card:
    card = db.get(Card, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")

    if payload.front is not None:
        card.front = payload.front.strip()
    if payload.back is not None:
        card.back = payload.back.strip()
    if payload.tags is not None:
        card.tags = payload.tags
    if payload.type is not None:
        card.type = payload.type
    if payload.difficulty_estimate is not None:
        card.difficulty_estimate = payload.difficulty_estimate

    db.commit()
    db.refresh(card)
    return card


@router.delete("/cards/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_card(card_id: str, db: Session = Depends(get_db)) -> None:
    card = db.get(Card, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")

    db.delete(card)
    db.commit()
