from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Card, CardConcept, CardState, Concept, ConceptEdge, utcnow
from app.scheduler import estimate_mastery
from app.schemas import ConceptAttachRequest, ConceptAttachResponse, WeakConceptRow

router = APIRouter(prefix="/concepts", tags=["concepts"])


def get_or_create_concept(db: Session, name: str, subject: str) -> Concept:
    clean_name = name.strip()
    clean_subject = subject.strip().lower()

    stmt = select(Concept).where(Concept.name == clean_name, Concept.subject == clean_subject)
    concept = db.execute(stmt).scalar_one_or_none()
    if concept is not None:
        return concept

    concept = Concept(name=clean_name, subject=clean_subject)
    db.add(concept)

    try:
        db.flush()
        return concept
    except IntegrityError:
        db.rollback()
        existing = db.execute(stmt).scalar_one_or_none()
        if existing is None:
            raise HTTPException(status_code=500, detail="Failed to create concept") from None
        return existing


@router.post("/attach", response_model=ConceptAttachResponse)
def attach_concepts_to_card(payload: ConceptAttachRequest, db: Session = Depends(get_db)) -> ConceptAttachResponse:
    card = db.get(Card, payload.card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")

    primary = get_or_create_concept(db, payload.primary_concept, payload.subject)

    existing_primary_stmt = select(CardConcept).where(
        CardConcept.card_id == payload.card_id,
        CardConcept.concept_id == primary.id,
        CardConcept.role == "primary",
    )
    if db.execute(existing_primary_stmt).scalar_one_or_none() is None:
        db.add(CardConcept(card_id=payload.card_id, concept_id=primary.id, role="primary"))

    supporting_count = 0
    for concept_name in payload.supporting_concepts:
        supporting = get_or_create_concept(db, concept_name, payload.subject)
        existing_support_stmt = select(CardConcept).where(
            CardConcept.card_id == payload.card_id,
            CardConcept.concept_id == supporting.id,
            CardConcept.role == "supporting",
        )
        if db.execute(existing_support_stmt).scalar_one_or_none() is None:
            db.add(CardConcept(card_id=payload.card_id, concept_id=supporting.id, role="supporting"))
            supporting_count += 1

    edges_added = 0
    for prereq_name in payload.prerequisites:
        prereq = get_or_create_concept(db, prereq_name, payload.subject)
        edge_stmt = select(ConceptEdge).where(
            ConceptEdge.from_concept_id == prereq.id,
            ConceptEdge.to_concept_id == primary.id,
            ConceptEdge.relation_type == "prerequisite",
        )
        if db.execute(edge_stmt).scalar_one_or_none() is None:
            db.add(
                ConceptEdge(
                    from_concept_id=prereq.id,
                    to_concept_id=primary.id,
                    relation_type="prerequisite",
                )
            )
            edges_added += 1

    db.commit()

    return ConceptAttachResponse(
        card_id=payload.card_id,
        primary_concept_id=primary.id,
        supporting_count=supporting_count,
        prerequisite_edges_added=edges_added,
    )


@router.get("/weak", response_model=list[WeakConceptRow])
def weak_concepts(
    user_id: str,
    deck_id: str | None = None,
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[WeakConceptRow]:
    stmt = (
        select(Concept.id, Concept.name, CardState.interval_days, CardState.due_at)
        .join(CardConcept, CardConcept.concept_id == Concept.id)
        .join(Card, Card.id == CardConcept.card_id)
        .join(CardState, and_(CardState.card_id == Card.id, CardState.user_id == user_id))
        .where(CardConcept.role == "primary")
    )
    if deck_id:
        stmt = stmt.where(Card.deck_id == deck_id)

    rows = db.execute(stmt).all()
    now = utcnow()

    aggregate: dict[str, dict[str, float | int | str]] = defaultdict(
        lambda: {"name": "", "sum": 0.0, "count": 0}
    )

    for concept_id, concept_name, interval_days, due_at in rows:
        mastery = estimate_mastery(interval_days=interval_days, due_at=due_at, now=now)
        aggregate[concept_id]["name"] = concept_name
        aggregate[concept_id]["sum"] = float(aggregate[concept_id]["sum"]) + mastery
        aggregate[concept_id]["count"] = int(aggregate[concept_id]["count"]) + 1

    ranked = []
    for concept_id, data in aggregate.items():
        count = int(data["count"])
        avg = float(data["sum"]) / max(1, count)
        ranked.append(
            WeakConceptRow(
                concept_id=concept_id,
                concept_name=str(data["name"]),
                avg_mastery=round(avg, 4),
                card_count=count,
            )
        )

    ranked.sort(key=lambda row: row.avg_mastery)
    return ranked[:limit]
