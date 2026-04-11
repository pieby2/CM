from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Card, CardConcept, CardState, Concept, Deck, ImportJob, Section, User, utcnow
from app.schemas import GenerateCardsRequest, GenerateCardsResponse, ImportJobProcessResponse, ImportJobRead, SectionRead
from app.services.pdf_pipeline import PDFProcessingError, process_import_job

router = APIRouter(prefix="/imports", tags=["imports"])

VALID_IMPORT_STATUSES = {
    "queued",
    "extracting",
    "chunking",
    "generating",
    "review_ready",
    "published",
    "failed",
}


class UpdateImportStatusRequest(BaseModel):
    status: str = Field(min_length=3, max_length=50)
    error_message: str | None = None


@router.post("/pdf", response_model=ImportJobRead, status_code=202)
async def upload_pdf_import(
    user_id: str = Form(...),
    deck_name: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ImportJob:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    source_name = Path(file.filename or "upload.pdf").name
    if not source_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    job = ImportJob(
        user_id=user_id,
        deck_name=deck_name.strip(),
        source_filename=source_name,
        status="queued",
    )
    db.add(job)
    db.flush()

    upload_dir = Path(settings.storage_path) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    target_path = upload_dir / f"{job.id}_{uuid4().hex}_{source_name}"
    contents = await file.read()
    target_path.write_bytes(contents)
    job.source_path = str(target_path.resolve())

    db.commit()
    db.refresh(job)
    return job


@router.get("/{job_id}", response_model=ImportJobRead)
def get_import_job(job_id: str, db: Session = Depends(get_db)) -> ImportJob:
    job = db.get(ImportJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")
    return job


@router.post("/{job_id}/status", response_model=ImportJobRead)
def update_import_job_status(
    job_id: str,
    payload: UpdateImportStatusRequest,
    db: Session = Depends(get_db),
) -> ImportJob:
    if payload.status not in VALID_IMPORT_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid import status")

    job = db.get(ImportJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")

    job.status = payload.status
    if payload.status != "failed":
        job.error_message = None
    else:
        job.error_message = payload.error_message or "Import failed"

    db.commit()
    db.refresh(job)
    return job


@router.post("/{job_id}/process", response_model=ImportJobProcessResponse)
def process_import_now(job_id: str, db: Session = Depends(get_db)) -> ImportJobProcessResponse:
    job = db.get(ImportJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")

    if job.status not in {"queued", "failed"}:
        raise HTTPException(status_code=409, detail=f"Import job cannot be processed from status '{job.status}'")

    try:
        result = process_import_job(db, job_id)
    except PDFProcessingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ImportJobProcessResponse(
        job_id=result.job_id,
        status="review_ready",
        section_count=result.section_count,
        extraction_method=result.extraction_method,
        page_count=result.page_count,
        extracted_char_count=result.extracted_char_count,
    )


@router.get("/{job_id}/sections", response_model=list[SectionRead])
def list_import_sections(job_id: str, db: Session = Depends(get_db)) -> list[Section]:
    job = db.get(ImportJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")

    stmt = select(Section).where(Section.import_job_id == job_id).order_by(Section.order_index.asc())
    return list(db.scalars(stmt).all())


@router.post("/{job_id}/generate", response_model=GenerateCardsResponse)
def generate_cards_from_import(
    job_id: str,
    payload: GenerateCardsRequest | None = None,
    x_groq_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> GenerateCardsResponse:
    """Generate flashcards from extracted PDF sections using Groq."""
    from app.services.card_generator import CardGenerationError, generate_cards_from_sections

    if payload is None:
        payload = GenerateCardsRequest()

    job = db.get(ImportJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")

    if job.status not in {"review_ready", "published"}:
        raise HTTPException(
            status_code=409,
            detail=f"Sections not ready. Current status: '{job.status}'. Process the PDF first.",
        )

    sections_stmt = select(Section).where(Section.import_job_id == job_id).order_by(Section.order_index.asc())
    sections = list(db.scalars(sections_stmt).all())
    if not sections:
        raise HTTPException(status_code=400, detail="No sections found for this import job")

    job.status = "generating"
    db.commit()

    section_dicts = [{"title": s.title, "content": s.content} for s in sections]

    try:
        generated = generate_cards_from_sections(
            sections=section_dicts,
            subject=payload.subject,
            card_count_hint=payload.card_count_hint,
            api_key=x_groq_api_key or None,
        )
    except CardGenerationError as exc:
        job.status = "review_ready"
        job.error_message = str(exc)
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user = db.get(User, job.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    deck = db.execute(
        select(Deck).where(Deck.user_id == job.user_id, Deck.name == job.deck_name)
    ).scalar_one_or_none()

    if deck is None:
        deck = Deck(user_id=job.user_id, name=job.deck_name, tags=[payload.subject])
        db.add(deck)
        db.flush()

    cards_created = 0
    for gen_card in generated:
        card = Card(
            deck_id=deck.id,
            front=gen_card.front,
            back=gen_card.back,
            tags=[payload.subject, gen_card.card_type],
            type=gen_card.card_type,
            difficulty_estimate=gen_card.difficulty,
        )
        db.add(card)
        db.flush()

        db.add(
            CardState(
                user_id=job.user_id,
                card_id=card.id,
                due_at=utcnow(),
                status="new",
                ease_factor=2.5,
                reps=0,
                interval_days=0,
            )
        )

        concept = db.execute(
            select(Concept).where(
                Concept.name == gen_card.concept.lower(),
                Concept.subject == payload.subject.lower(),
            )
        ).scalar_one_or_none()

        if concept is None:
            concept = Concept(
                name=gen_card.concept.lower(),
                subject=payload.subject.lower(),
                difficulty_estimate=gen_card.difficulty,
            )
            db.add(concept)
            db.flush()

        existing_link = db.execute(
            select(CardConcept).where(
                CardConcept.card_id == card.id,
                CardConcept.concept_id == concept.id,
                CardConcept.role == "primary",
            )
        ).scalar_one_or_none()
        if existing_link is None:
            db.add(CardConcept(card_id=card.id, concept_id=concept.id, role="primary"))

        cards_created += 1

    job.status = "published"
    job.error_message = None
    db.commit()

    return GenerateCardsResponse(
        job_id=job.id,
        deck_id=deck.id,
        cards_created=cards_created,
        section_count=len(sections),
    )
