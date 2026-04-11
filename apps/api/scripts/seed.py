from __future__ import annotations

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Card, CardConcept, CardState, Concept, Deck, User, utcnow

SEED_EMAIL = "demo@cue.local"
SEED_DECK_NAME = "Algebra Foundations"
SEED_SUBJECT = "math"

SEED_CARDS = [
    {
        "front": "What is the discriminant of ax^2 + bx + c?",
        "back": "The discriminant is b^2 - 4ac.",
        "type": "definition",
        "concept": "discriminant",
    },
    {
        "front": "If b^2 - 4ac > 0, how many real roots does the quadratic have?",
        "back": "It has two distinct real roots.",
        "type": "relationship",
        "concept": "discriminant",
    },
    {
        "front": "State the quadratic formula.",
        "back": "x = (-b ± sqrt(b^2 - 4ac)) / (2a)",
        "type": "definition",
        "concept": "quadratic formula",
    },
    {
        "front": "Complete the square: x^2 + 6x + 5.",
        "back": "x^2 + 6x + 5 = (x + 3)^2 - 4.",
        "type": "worked_example",
        "concept": "completing the square",
    },
    {
        "front": "What is the axis of symmetry for y = ax^2 + bx + c?",
        "back": "x = -b / (2a)",
        "type": "definition",
        "concept": "axis of symmetry",
    },
    {
        "front": "When does a quadratic have exactly one repeated root?",
        "back": "When the discriminant equals zero.",
        "type": "edge_case",
        "concept": "discriminant",
    },
]


def main() -> None:
    with SessionLocal() as db:
        user = db.execute(select(User).where(User.email == SEED_EMAIL)).scalar_one_or_none()
        if user is None:
            user = User(email=SEED_EMAIL)
            db.add(user)
            db.flush()

        deck = db.execute(
            select(Deck).where(Deck.user_id == user.id, Deck.name == SEED_DECK_NAME)
        ).scalar_one_or_none()
        if deck is None:
            deck = Deck(user_id=user.id, name=SEED_DECK_NAME, tags=["math", "seed"])
            db.add(deck)
            db.flush()

        created_cards = 0
        created_states = 0

        for card_data in SEED_CARDS:
            card = db.execute(
                select(Card).where(Card.deck_id == deck.id, Card.front == card_data["front"])
            ).scalar_one_or_none()

            if card is None:
                card = Card(
                    deck_id=deck.id,
                    front=card_data["front"],
                    back=card_data["back"],
                    tags=["seed"],
                    type=card_data["type"],
                    difficulty_estimate=1.0,
                )
                db.add(card)
                db.flush()
                created_cards += 1

            state = db.execute(
                select(CardState).where(CardState.user_id == user.id, CardState.card_id == card.id)
            ).scalar_one_or_none()
            if state is None:
                db.add(
                    CardState(
                        user_id=user.id,
                        card_id=card.id,
                        due_at=utcnow(),
                        status="new",
                        ease_factor=2.5,
                        reps=0,
                        interval_days=0,
                    )
                )
                created_states += 1

            concept = db.execute(
                select(Concept).where(Concept.name == card_data["concept"], Concept.subject == SEED_SUBJECT)
            ).scalar_one_or_none()
            if concept is None:
                concept = Concept(name=card_data["concept"], subject=SEED_SUBJECT, difficulty_estimate=1.0)
                db.add(concept)
                db.flush()

            link = db.execute(
                select(CardConcept).where(
                    CardConcept.card_id == card.id,
                    CardConcept.concept_id == concept.id,
                    CardConcept.role == "primary",
                )
            ).scalar_one_or_none()
            if link is None:
                db.add(CardConcept(card_id=card.id, concept_id=concept.id, role="primary"))

        db.commit()

    print(
        f"Seed complete for user={SEED_EMAIL} deck='{SEED_DECK_NAME}' "
        f"(cards_created={created_cards}, states_created={created_states})"
    )


if __name__ == "__main__":
    main()
