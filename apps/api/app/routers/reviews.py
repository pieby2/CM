from collections import defaultdict
from datetime import date, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Card, CardConcept, CardState, ReviewLog, utcnow
from app.scheduler import resolve_quality, sm2_transition
from app.services.hlr_client import request_hlr_transition
from app.schemas import (
    ReviewCandidate,
    ReviewGradeRequest,
    ReviewGradeResponse,
    ReviewHistoryDay,
    ReviewsTodayResponse,
    StreakResponse,
)

router = APIRouter(tags=["reviews"])


@router.get("/reviews/today", response_model=ReviewsTodayResponse)
def due_cards_today(
    user_id: str,
    deck_id: str | None = None,
    limit: int = Query(default=settings.default_due_limit, ge=1, le=200),
    db: Session = Depends(get_db),
) -> ReviewsTodayResponse:
    now = utcnow()

    stmt = (
        select(CardState, Card)
        .join(Card, Card.id == CardState.card_id)
        .where(
            CardState.user_id == user_id,
            CardState.suspended.is_(False),
            CardState.due_at <= now,
        )
        .order_by(CardState.due_at.asc())
        .limit(limit)
    )
    if deck_id:
        stmt = stmt.where(Card.deck_id == deck_id)

    rows = db.execute(stmt).all()
    items = [
        ReviewCandidate(
            card_id=card.id,
            deck_id=card.deck_id,
            front=card.front,
            back=card.back,
            type=card.type,
            due_at=state.due_at,
            status=state.status,
        )
        for state, card in rows
    ]
    return ReviewsTodayResponse(items=items)


@router.post("/reviews/grade", response_model=ReviewGradeResponse)
def grade_review(payload: ReviewGradeRequest, db: Session = Depends(get_db)) -> ReviewGradeResponse:
    reviewed_at = utcnow()

    try:
        quality = resolve_quality(payload.rating, payload.quality)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    card = db.get(Card, payload.card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")

    state_stmt = (
        select(CardState)
        .where(CardState.user_id == payload.user_id, CardState.card_id == payload.card_id)
        .with_for_update()
    )
    state = db.execute(state_stmt).scalar_one_or_none()

    if state is None:
        state = CardState(
            user_id=payload.user_id,
            card_id=payload.card_id,
            due_at=reviewed_at,
            status="new",
            ease_factor=2.5,
            reps=0,
            interval_days=0,
        )
        db.add(state)
        db.flush()

    elapsed_since_last_review_sec = None
    if state.last_review_at is not None:
        last_review_at = state.last_review_at
        if last_review_at.tzinfo is None:
            last_review_at = last_review_at.replace(tzinfo=timezone.utc)
        elapsed_since_last_review_sec = max(0, int((reviewed_at - last_review_at).total_seconds()))

    primary_concept_id_stmt = (
        select(CardConcept.concept_id)
        .where(CardConcept.card_id == card.id, CardConcept.role == "primary")
        .limit(1)
    )
    primary_concept_id = db.execute(primary_concept_id_stmt).scalar_one_or_none()

    card_total_reviews_stmt = select(func.count(ReviewLog.id)).where(
        ReviewLog.user_id == payload.user_id,
        ReviewLog.card_id == payload.card_id,
    )
    card_total_reviews = int(db.execute(card_total_reviews_stmt).scalar_one())

    user_total_reviews_stmt = select(func.count(ReviewLog.id)).where(ReviewLog.user_id == payload.user_id)
    user_total_reviews = int(db.execute(user_total_reviews_stmt).scalar_one())

    scheduler_version = "sm2-v1"

    transition = sm2_transition(
        ease_factor=state.ease_factor,
        reps=state.reps,
        interval_days=state.interval_days,
        quality=quality,
        reviewed_at=reviewed_at,
    )

    if card_total_reviews >= settings.hlr_min_reviews_per_card:
        hlr_payload = {
            "ease_factor": state.ease_factor,
            "reps": state.reps,
            "interval_days": state.interval_days,
            "quality": quality,
            "elapsed_since_last_review_sec": elapsed_since_last_review_sec,
            "card_difficulty": card.difficulty_estimate,
            "card_type": card.type,
            "card_total_reviews": card_total_reviews,
            "user_total_reviews": user_total_reviews,
            "target_recall": settings.hlr_default_target_recall,
        }
        hlr_transition = request_hlr_transition(hlr_payload)
        if hlr_transition is not None:
            next_interval_days = max(1, int(hlr_transition["interval_days"]))
            transition = {
                "ease_factor": float(hlr_transition["ease_factor"]),
                "reps": int(hlr_transition["reps"]),
                "interval_days": next_interval_days,
                "due_at": reviewed_at + timedelta(days=next_interval_days),
                "status": str(hlr_transition["status"]),
            }
            scheduler_version = str(hlr_transition.get("scheduler_version", "hlr-v1"))

    state.ease_factor = float(transition["ease_factor"])
    state.reps = int(transition["reps"])
    state.interval_days = int(transition["interval_days"])
    state.due_at = transition["due_at"]
    state.status = str(transition["status"])
    state.last_review_at = reviewed_at

    log = ReviewLog(
        user_id=payload.user_id,
        card_id=payload.card_id,
        timestamp=reviewed_at,
        quality=quality,
        elapsed_since_last_review_sec=elapsed_since_last_review_sec,
        response_time_ms=payload.response_time_ms,
        card_type=card.type,
        concept_id=primary_concept_id,
        scheduler_version=scheduler_version,
    )
    db.add(log)

    db.commit()
    db.refresh(state)

    return ReviewGradeResponse(
        card_id=payload.card_id,
        due_at=state.due_at,
        interval_days=state.interval_days,
        ease_factor=state.ease_factor,
        reps=state.reps,
        status=state.status,
        scheduler_version=scheduler_version,
    )


@router.get("/reviews/history", response_model=list[ReviewHistoryDay])
def review_history(
    user_id: str,
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> list[ReviewHistoryDay]:
    """Return daily review aggregates for the last N days."""
    now = utcnow()
    start = now - timedelta(days=days)

    stmt = (
        select(ReviewLog.timestamp, ReviewLog.quality)
        .where(ReviewLog.user_id == user_id, ReviewLog.timestamp >= start)
        .order_by(ReviewLog.timestamp.asc())
    )
    rows = db.execute(stmt).all()

    daily: dict[str, dict] = defaultdict(lambda: {"count": 0, "quality_sum": 0})
    for ts, quality in rows:
        day_key = ts.strftime("%Y-%m-%d")
        daily[day_key]["count"] += 1
        daily[day_key]["quality_sum"] += quality

    result = []
    for day_key in sorted(daily.keys()):
        data = daily[day_key]
        count = data["count"]
        avg_q = round(data["quality_sum"] / max(1, count), 2)
        result.append(ReviewHistoryDay(date=day_key, cards_reviewed=count, avg_quality=avg_q))

    return result


@router.get("/reviews/streak", response_model=StreakResponse)
def review_streak(user_id: str, db: Session = Depends(get_db)) -> StreakResponse:
    """Compute current and longest study streak."""
    stmt = (
        select(func.date(ReviewLog.timestamp))
        .where(ReviewLog.user_id == user_id)
        .group_by(func.date(ReviewLog.timestamp))
        .order_by(func.date(ReviewLog.timestamp).desc())
    )
    rows = db.execute(stmt).all()
    review_dates = [row[0] for row in rows]

    if not review_dates:
        return StreakResponse(
            current_streak=0, longest_streak=0, total_review_days=0, last_review_date=None
        )

    today = date.today()

    # Normalize to date objects
    normalized = []
    for d in review_dates:
        if isinstance(d, str):
            normalized.append(date.fromisoformat(d))
        elif hasattr(d, "date"):
            normalized.append(d.date())
        else:
            normalized.append(d)

    normalized.sort(reverse=True)
    last_date = normalized[0]

    # Current streak: consecutive days ending today or yesterday
    current_streak = 0
    check_date = today
    if last_date < today - timedelta(days=1):
        current_streak = 0
    else:
        if last_date < today:
            check_date = last_date
        for d in normalized:
            if d == check_date:
                current_streak += 1
                check_date -= timedelta(days=1)
            elif d < check_date:
                break

    # Longest streak
    longest = 1
    run = 1
    for i in range(1, len(normalized)):
        if normalized[i] == normalized[i - 1] - timedelta(days=1):
            run += 1
            longest = max(longest, run)
        elif normalized[i] == normalized[i - 1]:
            continue
        else:
            run = 1

    return StreakResponse(
        current_streak=current_streak,
        longest_streak=longest,
        total_review_days=len(set(normalized)),
        last_review_date=last_date.isoformat(),
    )
