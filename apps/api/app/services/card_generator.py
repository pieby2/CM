"""LLM-powered flashcard generator using Groq."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from app.config import settings

logger = logging.getLogger("cue.card_generator")

VALID_CARD_TYPES = {"definition", "relationship", "worked_example", "edge_case"}

SYSTEM_PROMPT = """\
You are an expert educator who creates high-quality flashcards from study material.

Given a text section, generate flashcards that comprehensively cover the material.
Create a MIX of card types:
- "definition": Key terms, formulas, or concept definitions
- "relationship": How concepts connect, cause-and-effect, comparisons
- "worked_example": Step-by-step problem solutions the student should recall
- "edge_case": Tricky exceptions, boundary conditions, common mistakes

Guidelines:
- Write the FRONT as a clear, specific question.
- Write the BACK as a concise, complete answer.
- Each card should test ONE concept or fact.
- Cards should feel like they were written by a great teacher.
- Identify the primary concept each card tests (1-3 words).
- Cover the material COMPREHENSIVELY — don't just skim the surface.

Respond ONLY with a JSON array. Each element must have exactly these keys:
  "front": string,
  "back": string,
  "type": one of "definition" | "relationship" | "worked_example" | "edge_case",
  "concept": string (1-3 word primary concept name),
  "difficulty": float between 0.5 and 3.0 (1.0 = average)

Example output:
[
  {"front": "What is the discriminant of ax² + bx + c?", "back": "The discriminant is b² − 4ac. It determines the nature and number of roots.", "type": "definition", "concept": "discriminant", "difficulty": 1.0},
  {"front": "If b² − 4ac < 0, what can you say about the roots?", "back": "The equation has no real roots; both roots are complex conjugates.", "type": "edge_case", "concept": "complex roots", "difficulty": 1.5}
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
) -> list[GeneratedCard]:
    """Generate flashcards from a single section using Groq."""
    resolved_key = api_key or settings.groq_api_key
    if not resolved_key:
        raise CardGenerationError(
            "Groq API key not configured. Enter your API key in Settings or set CUE_GROQ_API_KEY."
        )

    try:
        from groq import Groq
    except ImportError as exc:
        raise CardGenerationError(
            "groq package not installed. Run: pip install groq"
        ) from exc

    client = Groq(api_key=resolved_key)

    user_prompt = (
        f"Subject: {subject}\n"
        f"Section title: {section_title}\n"
        f"Generate approximately {card_count_hint} flashcards from this material:\n\n"
        f"{section_content[:6000]}"
    )

    try:
        response = client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=settings.groq_temperature,
        )
        raw_text = response.choices[0].message.content.strip()
    except Exception as exc:
        logger.error("Groq API call failed: %s", exc)
        raise CardGenerationError(f"Groq API error: {exc}") from exc

    return _parse_cards(raw_text)


def generate_cards_from_sections(
    sections: list[dict],
    subject: str = "general",
    card_count_hint: int = 10,
    api_key: str | None = None,
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


