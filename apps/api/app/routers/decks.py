from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Card, CardState, Deck, User
from app.schemas import DeckCreate, DeckRead, DeckStatsResponse, DeckUpdate

router = APIRouter(tags=["decks"])


@router.post("/decks", response_model=DeckRead, status_code=status.HTTP_201_CREATED)
def create_deck(payload: DeckCreate, db: Session = Depends(get_db)) -> Deck:
    user = db.get(User, payload.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    deck = Deck(
        user_id=payload.user_id,
        name=payload.name.strip(),
        tags=payload.tags,
    )
    db.add(deck)
    db.commit()
    db.refresh(deck)
    return deck


@router.get("/decks", response_model=list[DeckRead])
def list_decks(
    user_id: str | None = None,
    search: str | None = Query(default=None, min_length=1, max_length=100),
    db: Session = Depends(get_db),
) -> list[Deck]:
    stmt = select(Deck).order_by(Deck.created_at.desc())
    if user_id:
        stmt = stmt.where(Deck.user_id == user_id)
    if search:
        stmt = stmt.where(Deck.name.ilike(f"%{search}%"))

    return list(db.scalars(stmt).all())


@router.get("/decks/{deck_id}", response_model=DeckRead)
def get_deck(deck_id: str, db: Session = Depends(get_db)) -> Deck:
    deck = db.get(Deck, deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")
    return deck


@router.put("/decks/{deck_id}", response_model=DeckRead)
def update_deck(deck_id: str, payload: DeckUpdate, db: Session = Depends(get_db)) -> Deck:
    deck = db.get(Deck, deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")

    if payload.name is not None:
        deck.name = payload.name.strip()
    if payload.tags is not None:
        deck.tags = payload.tags

    db.commit()
    db.refresh(deck)
    return deck


@router.delete("/decks/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deck(deck_id: str, db: Session = Depends(get_db)) -> None:
    deck = db.get(Deck, deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")

    db.delete(deck)
    db.commit()


@router.get("/decks/{deck_id}/stats", response_model=DeckStatsResponse)
def get_deck_stats(deck_id: str, user_id: str = Query(...), db: Session = Depends(get_db)) -> DeckStatsResponse:
    deck = db.get(Deck, deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")

    counts_stmt = (
        select(CardState.status, func.count(CardState.id))
        .join(Card, Card.id == CardState.card_id)
        .where(Card.deck_id == deck_id, CardState.user_id == user_id)
        .group_by(CardState.status)
    )
    grouped = dict(db.execute(counts_stmt).all())

    new_count = int(grouped.get("new", 0))
    learning_count = int(grouped.get("learning", 0))
    mature_count = int(grouped.get("mature", 0))
    total_count = new_count + learning_count + mature_count

    return DeckStatsResponse(
        deck_id=deck_id,
        new_count=new_count,
        learning_count=learning_count,
        mature_count=mature_count,
        total_count=total_count,
    )
