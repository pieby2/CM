"""LLM-powered flashcard generator using Groq."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from app.config import settings

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

    import base64
    from pathlib import Path

    model_to_use = settings.groq_model
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]

    # Detect images in markdown
    image_paths = re.findall(r'!\[.*?\]\(/api/storage/(.*?)/(.*?)\)', section_content)
    if image_paths:
        model_to_use = "llama-3.2-90b-vision-preview"
        user_content = [{"type": "text", "text": user_prompt}]
        for job_id, img_name in image_paths[:3]:  # limit to 3 images to avoid payload size errors
            local_img_path = Path(settings.storage_path) / job_id / img_name
            if local_img_path.exists():
                with open(local_img_path, "rb") as f:
                    b64_img = base64.b64encode(f.read()).decode('utf-8')
                    user_content.append({
                        "type": "image_url", 
                        "image_url": {"url": f"data:image/png;base64,{b64_img}"}
                    })
        messages.append({"role": "user", "content": user_content})
    else:
        messages.append({"role": "user", "content": user_prompt})

    try:
        response = client.chat.completions.create(
            model=model_to_use,
            messages=messages,
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


def generate_mnemonic(front: str, back: str, api_key: str | None = None) -> str:
    """Generate a mnemonic or ELI5 analogy for a given card."""
    resolved_key = api_key or settings.groq_api_key
    if not resolved_key:
        raise CardGenerationError("Groq API key not configured.")

    try:
        from groq import Groq
    except ImportError as exc:
        raise CardGenerationError("groq package not installed.") from exc

    client = Groq(api_key=resolved_key)

    sys_prompt = (
        "You are a creative tutor. Your goal is to help a student easily memorize a tricky flashcard.\n"
        "Generate a short, memorable mnemonic device, acronym, or a brilliant 'Explain Like I'm 5' analogy.\n"
        "Keep it under 3 sentences. Be extremely concise. Don't use markdown styling like headers."
    )

    user_prompt = f"Flashcard Front (Question): {front}\nFlashcard Back (Answer): {back}\n\nPlease give me a memory trick."

    try:
        response = client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.8,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        logger.error("Groq API mnemonic generation failed: %s", exc)
        raise CardGenerationError("Failed to generate mnemonic") from exc

