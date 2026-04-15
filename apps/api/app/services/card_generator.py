"""LLM-powered flashcard generation and tutoring helpers."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.services.ai_client import AIClientError, generate_completion

logger = logging.getLogger("cue.card_generator")

VALID_CARD_TYPES = {"definition", "relationship", "worked_example", "edge_case", "cloze"}

SYSTEM_PROMPT = """\
You are an expert educator who creates high-quality flashcards from study material.

Given a text section, generate flashcards that comprehensively cover the material.
Create a MIX of card types:
- "definition": Key terms, formulas, or concept definitions
- "relationship": How concepts connect, cause-and-effect, comparisons
- "worked_example": Step-by-step problem solutions the student should recall
- "edge_case": Tricky exceptions, boundary conditions, common mistakes
- "cloze": Fill-in-the-blank statements. Use {{blank}} notation on BOTH front and back if needed. The front should have `{{blank}}`, and the back should have the answer like `{{Answer}}`. Example: Front: `The capital of France is {{...}}`, Back: `The capital of France is {{Paris}}`.

Guidelines:
- Write the FRONT as a clear, specific question or a cloze statement.
- Write the BACK as a concise, complete answer.
- Each card should test ONE concept or fact.
- Cards should feel like they were written by a great teacher.
- Identify the primary concept each card tests (1-3 words).
- Cover the material COMPREHENSIVELY — don't just skim the surface.
- If images are provided, create cards that refer to the images where appropriate.

Respond ONLY with a JSON array. Each element must have exactly these keys:
  "front": string,
  "back": string,
  "type": one of "definition" | "relationship" | "worked_example" | "edge_case" | "cloze",
  "concept": string (1-3 word primary concept name),
  "difficulty": float between 0.5 and 3.0 (1.0 = average)

Example output:
[
  {"front": "What is the discriminant of ax² + bx + c?", "back": "The discriminant is b² − 4ac. It determines the nature and number of roots.", "type": "definition", "concept": "discriminant", "difficulty": 1.0},
  {"front": "The typical output of the softmax function sums to {{...}}.", "back": "The typical output of the softmax function sums to {{1}}.", "type": "cloze", "concept": "softmax", "difficulty": 1.2}
]
"""


@dataclass
class GeneratedCard:
    front: str
    back: str
    card_type: str
    concept: str
    difficulty: float


class CardGenerationError(Exception):
    pass


def generate_cards_from_section(
    section_title: str,
    section_content: str,
    subject: str = "general",
    card_count_hint: int = 10,
    api_key: str | None = None,
    provider: str | None = None,
) -> list[GeneratedCard]:
    """Generate flashcards from a single section using the configured AI provider."""

    user_prompt = (
        f"Subject: {subject}\n"
        f"Section title: {section_title}\n"
        f"Generate approximately {card_count_hint} flashcards from this material:\n\n"
        f"{section_content[:6000]}"
    )

    image_paths = _collect_section_images(section_content)

    try:
        raw_text = generate_completion(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            api_key=api_key,
            provider=provider,
            image_paths=image_paths,
        )
    except AIClientError as exc:
        logger.error("AI card generation failed: %s", exc)
        raise CardGenerationError(str(exc)) from exc

    return _parse_cards(raw_text)


def generate_cards_from_sections(
    sections: list[dict],
    subject: str = "general",
    card_count_hint: int = 10,
    api_key: str | None = None,
    provider: str | None = None,
) -> list[GeneratedCard]:
    """Generate flashcards from multiple sections with rate limit protection."""
    import time
    all_cards: list[GeneratedCard] = []
    
    # 1. Batch sections to reduce API calls (target ~4000-6000 chars per batch)
    batches = []
    current_batch_title = "Combined Sections"
    current_batch_content = ""
    
    for s in sections:
        content = s.get("content", "").strip()
        if not content:
            continue
            
        if len(current_batch_content) + len(content) > 5000 and current_batch_content:
            batches.append((current_batch_title, current_batch_content))
            current_batch_content = ""
            current_batch_title = s.get("title", "Untitled")
            
        current_batch_content += f"\n\n### {s.get('title', 'Untitled')}\n{content}"
        
    if current_batch_content:
        batches.append((current_batch_title, current_batch_content))
        
    per_batch = max(3, card_count_hint // max(1, len(batches)))

    # 2. Process batches slowly to respect 15 Requests Per Minute (RPM) free tier
    last_error = None
    for i, (title, content) in enumerate(batches):
        if i > 0:
            time.sleep(4.5)  # 4.5 seconds = ~13 RPM
            
        try:
            cards = generate_cards_from_section(
                section_title=title,
                section_content=content,
                subject=subject,
                card_count_hint=per_batch,
                api_key=api_key,
                provider=provider,
            )
            all_cards.extend(cards)
            logger.info("Generated %d cards from batch '%s'", len(cards), title[:60])
        except CardGenerationError as err:
            logger.warning("Failed to generate cards for batch '%s': %s", title[:60], err)
            last_error = err
            continue

    if not all_cards:
        err_msg = "Failed to generate any cards. API rate limits may have been exceeded."
        if last_error:
            err_msg += f" Last error: {str(last_error)}"
        raise CardGenerationError(err_msg)

    return all_cards


def _collect_section_images(section_content: str, limit: int = 3) -> list[Path]:
    image_paths: list[Path] = []
    matches = re.findall(r"!\[.*?\]\(/api/storage/([^/]+)/([^)]+)\)", section_content)
    for job_id, image_name in matches[:limit]:
        candidate = Path(settings.storage_path) / job_id / image_name
        if candidate.is_file():
            image_paths.append(candidate)
    return image_paths


def _parse_cards(raw_text: str) -> list[GeneratedCard]:
    """Parse AI JSON response into GeneratedCard objects."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse AI response as JSON: %s", exc)
        raise CardGenerationError("Failed to parse AI response") from exc

    if not isinstance(data, list):
        raise CardGenerationError("AI response is not a JSON array")

    cards: list[GeneratedCard] = []
    for item in data:
        if not isinstance(item, dict):
            continue

        front = str(item.get("front", "")).strip()
        back = str(item.get("back", "")).strip()
        card_type = str(item.get("type", "definition")).strip().lower()
        concept = str(item.get("concept", "general")).strip()
        difficulty = float(item.get("difficulty", 1.0))

        if not front or not back:
            continue
        if card_type not in VALID_CARD_TYPES:
            card_type = "definition"

        difficulty = max(0.5, min(3.0, difficulty))

        cards.append(
            GeneratedCard(
                front=front,
                back=back,
                card_type=card_type,
                concept=concept,
                difficulty=round(difficulty, 2),
            )
        )

    if not cards:
        raise CardGenerationError("AI generated no valid cards")

    return cards


def generate_mnemonic(
    front: str,
    back: str,
    api_key: str | None = None,
    provider: str | None = None,
) -> str:
    """Generate a mnemonic or ELI5 analogy for a given card."""
    sys_prompt = (
        "You are a creative tutor. Your goal is to help a student easily memorize a tricky flashcard.\n"
        "Generate a short, memorable mnemonic device, acronym, or a brilliant 'Explain Like I'm 5' analogy.\n"
        "Keep it under 3 sentences. Be extremely concise. Don't use markdown styling like headers."
    )

    user_prompt = f"Flashcard Front (Question): {front}\nFlashcard Back (Answer): {back}\n\nPlease give me a memory trick."

    try:
        return generate_completion(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            api_key=api_key,
            provider=provider,
            temperature=0.8,
        )
    except AIClientError as exc:
        logger.error("AI mnemonic generation failed: %s", exc)
        raise CardGenerationError(str(exc)) from exc

