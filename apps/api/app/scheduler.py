from datetime import datetime, timedelta
from math import log1p


RATING_TO_QUALITY = {
    "again": 1,
    "hard": 2,
    "good": 4,
    "easy": 5,
}


def resolve_quality(rating: str | None, quality: int | None) -> int:
    if quality is not None:
        if quality < 0 or quality > 5:
            raise ValueError("quality must be between 0 and 5")
        return quality

    if rating is None:
        raise ValueError("rating or quality is required")

    if rating not in RATING_TO_QUALITY:
        raise ValueError("invalid rating")

    return RATING_TO_QUALITY[rating]


def sm2_transition(
    ease_factor: float,
    reps: int,
    interval_days: int,
    quality: int,
    reviewed_at: datetime,
) -> dict[str, object]:
    q = max(0, min(5, quality))
    ef = ease_factor or 2.5
    current_interval = max(0, interval_days)

    if q < 3:
        next_reps = 0
        next_interval = 1
        next_status = "learning"
    else:
        next_reps = reps + 1
        if next_reps == 1:
            next_interval = 1
        elif next_reps == 2:
            next_interval = 6
        else:
            next_interval = max(1, round(current_interval * ef))
        next_status = "mature" if next_reps >= 5 else "learning"

    ef_prime = max(1.3, ef + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)))
    due_at = reviewed_at + timedelta(days=next_interval)

    return {
        "ease_factor": round(ef_prime, 4),
        "reps": next_reps,
        "interval_days": next_interval,
        "due_at": due_at,
        "status": next_status,
    }


def estimate_mastery(interval_days: int, due_at: datetime, now: datetime) -> float:
    baseline = min(0.95, 0.25 + (log1p(max(0, interval_days)) / log1p(60)))
    overdue_days = max(0.0, (now - due_at).total_seconds() / 86400)
    penalty = min(0.5, overdue_days * 0.05)
    return max(0.05, round(baseline - penalty, 4))
