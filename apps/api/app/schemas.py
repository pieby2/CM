from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class UserRead(BaseModel):
    id: str
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DeckCreate(BaseModel):
    user_id: str
    name: str = Field(min_length=1, max_length=255)
    tags: list[str] = Field(default_factory=list)


class DeckRead(BaseModel):
    id: str
    user_id: str
    name: str
    tags: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class CardCreate(BaseModel):
    deck_id: str
    front: str = Field(min_length=1)
    back: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    type: str = "definition"
    section_id: str | None = None
    difficulty_estimate: float = 1.0


class CardRead(BaseModel):
    id: str
    deck_id: str
    front: str
    back: str
    tags: list[str]
    type: str
    section_id: str | None
    difficulty_estimate: float
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewCandidate(BaseModel):
    card_id: str
    deck_id: str
    front: str
    back: str
    type: str
    due_at: datetime
    status: str


class ReviewsTodayResponse(BaseModel):
    items: list[ReviewCandidate]


class ReviewGradeRequest(BaseModel):
    user_id: str
    card_id: str
    rating: Literal["again", "hard", "good", "easy"] | None = None
    quality: int | None = Field(default=None, ge=0, le=5)
    response_time_ms: int | None = Field(default=None, ge=0)


class ReviewGradeResponse(BaseModel):
    card_id: str
    due_at: datetime
    interval_days: int
    ease_factor: float
    reps: int
    status: str
    scheduler_version: str


class DeckStatsResponse(BaseModel):
    deck_id: str
    new_count: int
    learning_count: int
    mature_count: int
    total_count: int


class ImportJobRead(BaseModel):
    id: str
    user_id: str
    deck_name: str
    source_filename: str
    extraction_method: str | None
    page_count: int | None
    extracted_char_count: int | None
    status: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ImportJobProcessResponse(BaseModel):
    job_id: str
    status: str
    section_count: int
    extraction_method: str
    page_count: int
    extracted_char_count: int


class SectionRead(BaseModel):
    id: str
    import_job_id: str
    title: str
    order_index: int
    content: str

    model_config = {"from_attributes": True}


class CardUpdate(BaseModel):
    front: str | None = None
    back: str | None = None
    tags: list[str] | None = None
    type: str | None = None
    difficulty_estimate: float | None = None


class DeckUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    tags: list[str] | None = None


class GenerateCardsRequest(BaseModel):
    subject: str = "general"
    card_count_hint: int = Field(default=10, ge=3, le=30)


class GenerateCardsResponse(BaseModel):
    job_id: str
    deck_id: str
    cards_created: int
    section_count: int


class ReviewHistoryDay(BaseModel):
    date: str
    cards_reviewed: int
    avg_quality: float


class StreakResponse(BaseModel):
    current_streak: int
    longest_streak: int
    total_review_days: int
    last_review_date: str | None


class ConceptAttachRequest(BaseModel):
    card_id: str
    subject: str = "math"
    primary_concept: str = Field(min_length=1, max_length=255)
    supporting_concepts: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)


class ConceptAttachResponse(BaseModel):
    card_id: str
    primary_concept_id: str
    supporting_count: int
    prerequisite_edges_added: int


class WeakConceptRow(BaseModel):
    concept_id: str
    concept_name: str
    avg_mastery: float
    card_count: int
