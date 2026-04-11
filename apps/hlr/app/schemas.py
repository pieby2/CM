from pydantic import BaseModel, Field


class PredictTransitionRequest(BaseModel):
    ease_factor: float = Field(default=2.5, ge=1.3, le=4.0)
    reps: int = Field(default=0, ge=0)
    interval_days: int = Field(default=0, ge=0)
    quality: int = Field(ge=0, le=5)
    elapsed_since_last_review_sec: int | None = Field(default=None, ge=0)
    card_difficulty: float = Field(default=1.0, ge=0.1, le=5.0)
    card_type: str = Field(default="definition", min_length=1, max_length=50)
    card_total_reviews: int = Field(default=0, ge=0)
    user_total_reviews: int = Field(default=0, ge=0)
    target_recall: float | None = Field(default=None, ge=0.5, le=0.95)


class PredictTransitionResponse(BaseModel):
    scheduler_version: str
    ease_factor: float
    reps: int
    interval_days: int
    status: str
    predicted_recall: float
    half_life_days: float
    target_recall: float


class WeightsPayload(BaseModel):
    intercept: float = 0.85
    ease_factor_weight: float = 0.38
    log_reps_weight: float = 0.36
    log_card_reviews_weight: float = 0.24
    log_user_reviews_weight: float = 0.12
    difficulty_weight: float = -0.42
    card_type_bias: dict[str, float] = Field(default_factory=dict)


class WeightsResponse(BaseModel):
    scheduler_version: str
    weights: WeightsPayload
    model_path: str
