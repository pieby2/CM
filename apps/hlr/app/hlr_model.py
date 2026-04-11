from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.config import Settings
from app.schemas import PredictTransitionRequest, PredictTransitionResponse, WeightsPayload


SCHEDULER_VERSION = "hlr-v1"

QUALITY_MULTIPLIERS = {
    0: 0.35,
    1: 0.48,
    2: 0.68,
    3: 1.0,
    4: 1.28,
    5: 1.52,
}

DEFAULT_CARD_TYPE_BIAS = {
    "definition": 0.0,
    "relationship": 0.08,
    "worked_example": -0.06,
    "edge_case": -0.15,
}


@dataclass
class HlrWeights:
    intercept: float = 0.85
    ease_factor_weight: float = 0.38
    log_reps_weight: float = 0.36
    log_card_reviews_weight: float = 0.24
    log_user_reviews_weight: float = 0.12
    difficulty_weight: float = -0.42
    card_type_bias: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_CARD_TYPE_BIAS))

    @classmethod
    def from_payload(cls, payload: WeightsPayload) -> "HlrWeights":
        return cls(
            intercept=payload.intercept,
            ease_factor_weight=payload.ease_factor_weight,
            log_reps_weight=payload.log_reps_weight,
            log_card_reviews_weight=payload.log_card_reviews_weight,
            log_user_reviews_weight=payload.log_user_reviews_weight,
            difficulty_weight=payload.difficulty_weight,
            card_type_bias=payload.card_type_bias or dict(DEFAULT_CARD_TYPE_BIAS),
        )


class HlrModelService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.weights = self._load_weights()

    def _load_weights(self) -> HlrWeights:
        model_path = Path(self.settings.model_path)
        if not model_path.exists():
            return HlrWeights()

        payload = json.loads(model_path.read_text(encoding="utf-8"))
        return HlrWeights(
            intercept=float(payload.get("intercept", 0.85)),
            ease_factor_weight=float(payload.get("ease_factor_weight", 0.38)),
            log_reps_weight=float(payload.get("log_reps_weight", 0.36)),
            log_card_reviews_weight=float(payload.get("log_card_reviews_weight", 0.24)),
            log_user_reviews_weight=float(payload.get("log_user_reviews_weight", 0.12)),
            difficulty_weight=float(payload.get("difficulty_weight", -0.42)),
            card_type_bias={
                str(k): float(v)
                for k, v in (payload.get("card_type_bias") or dict(DEFAULT_CARD_TYPE_BIAS)).items()
            },
        )

    def save_weights(self) -> None:
        model_path = Path(self.settings.model_path)
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.write_text(json.dumps(asdict(self.weights), indent=2), encoding="utf-8")

    def update_weights(self, payload: WeightsPayload) -> HlrWeights:
        self.weights = HlrWeights.from_payload(payload)
        self.save_weights()
        return self.weights

    def predict_transition(self, request: PredictTransitionRequest) -> PredictTransitionResponse:
        quality = int(max(0, min(5, request.quality)))

        lag_days = (
            float(request.elapsed_since_last_review_sec) / 86400.0
            if request.elapsed_since_last_review_sec is not None
            else float(request.interval_days)
        )

        base_half_life = self._predict_half_life_days(request)
        predicted_recall = self._predict_recall_probability(lag_days=lag_days, half_life_days=base_half_life)

        quality_multiplier = QUALITY_MULTIPLIERS.get(quality, 1.0)
        updated_half_life = self._clamp_half_life(base_half_life * quality_multiplier)

        target_recall = request.target_recall or self.settings.default_target_recall
        target_recall = max(0.5, min(0.95, target_recall))

        if quality < 3:
            next_reps = 0
            next_interval_days = 1
            next_status = "learning"
        else:
            next_reps = request.reps + 1
            next_interval_days = max(1, round(self._due_interval_for_target(updated_half_life, target_recall)))
            next_status = "mature" if next_reps >= 5 and next_interval_days >= 10 else "learning"

        next_ease_factor = _sm2_ease_factor_update(request.ease_factor, quality)

        return PredictTransitionResponse(
            scheduler_version=SCHEDULER_VERSION,
            ease_factor=round(next_ease_factor, 4),
            reps=next_reps,
            interval_days=next_interval_days,
            status=next_status,
            predicted_recall=round(predicted_recall, 4),
            half_life_days=round(updated_half_life, 4),
            target_recall=target_recall,
        )

    def _predict_half_life_days(self, request: PredictTransitionRequest) -> float:
        type_bias = self.weights.card_type_bias.get(request.card_type.strip().lower(), -0.05)

        linear = (
            self.weights.intercept
            + self.weights.ease_factor_weight * float(request.ease_factor)
            + self.weights.log_reps_weight * math.log1p(max(0, request.reps))
            + self.weights.log_card_reviews_weight * math.log1p(max(0, request.card_total_reviews))
            + self.weights.log_user_reviews_weight * math.log1p(max(0, request.user_total_reviews))
            + self.weights.difficulty_weight * float(request.card_difficulty)
            + type_bias
        )

        half_life = math.exp(linear)
        return self._clamp_half_life(half_life)

    def _predict_recall_probability(self, lag_days: float, half_life_days: float) -> float:
        if lag_days <= 0:
            return 0.99
        probability = 2 ** (-(lag_days / max(0.1, half_life_days)))
        return max(0.01, min(0.999, probability))

    def _due_interval_for_target(self, half_life_days: float, target_recall: float) -> float:
        return -half_life_days * (math.log(target_recall) / math.log(2))

    def _clamp_half_life(self, half_life_days: float) -> float:
        return max(self.settings.min_half_life_days, min(self.settings.max_half_life_days, half_life_days))


def _sm2_ease_factor_update(current_ease_factor: float, quality: int) -> float:
    q = max(0, min(5, quality))
    ef = current_ease_factor or 2.5
    return max(1.3, ef + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)))
