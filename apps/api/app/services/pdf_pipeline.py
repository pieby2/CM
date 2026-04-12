from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from statistics import median

from PIL import Image
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import settings
from app.models import ImportJob, Section


class PDFProcessingError(Exception):
    pass


@dataclass
class ExtractedLine:
    page_number: int
    text: str
    font_size: float | None
    is_bold: bool


@dataclass
class SectionDraft:
    title: str
    content: str


@dataclass
class ImportProcessResult:
    job_id: str
    section_count: int
    extraction_method: str
    page_count: int
    extracted_char_count: int


HEADING_PATTERNS = [
    re.compile(r"^(chapter|unit|lesson|topic)\s+\d+", re.IGNORECASE),
    re.compile(r"^(\d+\.?)+(\s+[A-Za-z].+)?$"),
    re.compile(r"^[A-Z][A-Z\s\-:()]{3,80}$"),
]


def process_import_job(db: Session, job_id: str) -> ImportProcessResult:
    job = db.get(ImportJob, job_id)
    if job is None:
        raise PDFProcessingError("Import job not found")

    if not job.source_path:
        _mark_job_failed(db, job, "Import job has no source_path")
        raise PDFProcessingError("Import job has no source_path")

    pdf_path = Path(job.source_path)
    if not pdf_path.exists():
        _mark_job_failed(db, job, f"PDF file not found: {pdf_path}")
        raise PDFProcessingError("PDF file for import job does not exist")

    try:
        job.status = "extracting"
        job.error_message = None
        db.commit()

        lines, method, page_count = extract_pdf_lines(pdf_path, job.id)
        text_char_count = sum(len(line.text) for line in lines)

        job.status = "chunking"
        job.extraction_method = method
        job.page_count = page_count
        job.extracted_char_count = text_char_count
        db.commit()

        sections = chunk_lines_into_sections(
            lines,
            min_section_chars=settings.section_min_chars,
            max_section_chars=settings.section_max_chars,
        )

        db.execute(delete(Section).where(Section.import_job_id == job.id))
        for index, draft in enumerate(sections):
            db.add(
                Section(
                    import_job_id=job.id,
                    title=draft.title[:255],
                    order_index=index,
                    content=draft.content,
                )
            )

        job.status = "review_ready"
        job.error_message = None
        db.commit()

        return ImportProcessResult(
            job_id=job.id,
            section_count=len(sections),
            extraction_method=method,
            page_count=page_count,
            extracted_char_count=text_char_count,
        )
    except Exception as exc:
        db.rollback()
        failed_job = db.get(ImportJob, job_id)
        if failed_job is not None:
            _mark_job_failed(db, failed_job, str(exc))
        raise PDFProcessingError(str(exc)) from exc


def _load_dependency(module_name: str):
    try:
        return import_module(module_name)
    except ModuleNotFoundError as exc:
        raise PDFProcessingError(
            f"Missing Python dependency '{module_name}'. Install apps/api/requirements.txt first."
        ) from exc


def extract_pdf_lines(pdf_path: Path, job_id: str) -> tuple[list[ExtractedLine], str, int]:
    best_lines: list[ExtractedLine] = []
    best_method = "none"
    best_score = 0
    page_count = 0
    extractor_errors: list[str] = []

    for method_name, extractor in (
        ("pymupdf", _extract_with_pymupdf),
        ("pdfplumber", _extract_with_pdfplumber),
    ):
        try:
            if method_name == "pymupdf":
                lines, method_page_count = extractor(pdf_path, job_id)
            else:
                lines, method_page_count = extractor(pdf_path)
            page_count = max(page_count, method_page_count)
            score = _text_score(lines)
            if score > best_score:
                best_lines = lines
                best_method = method_name
                best_score = score
        except Exception as exc:
            extractor_errors.append(f"{method_name}: {exc}")

    if _needs_ocr(best_lines, page_count):
        try:
            ocr_lines, ocr_pages = _extract_with_ocr(pdf_path)
            ocr_score = _text_score(ocr_lines)
            page_count = max(page_count, ocr_pages)
            if ocr_score > best_score:
                best_lines = ocr_lines
                best_method = "ocr"
                best_score = ocr_score
        except Exception as exc:
            extractor_errors.append(f"ocr: {exc}")

    cleaned = _remove_noise_lines(best_lines, page_count)
    if cleaned:
        return cleaned, best_method, page_count

    error_suffix = ""
    if extractor_errors:
        error_suffix = " Details: " + "; ".join(extractor_errors)
    raise PDFProcessingError("Unable to extract text from PDF." + error_suffix)


def chunk_lines_into_sections(
    lines: list[ExtractedLine],
    min_section_chars: int,
    max_section_chars: int,
) -> list[SectionDraft]:
    if not lines:
        return []

    body_font_size = _estimate_body_font_size(lines)
    sections: list[SectionDraft] = []
    current_title = "Introduction"
    current_lines: list[str] = []

    for line in lines:
        text = line.text.strip()
        if not text:
            continue

        if _is_heading(text, line, body_font_size):
            if current_lines:
                sections.extend(
                    _split_content_into_sections(
                        current_title,
                        "\n".join(current_lines),
                        min_section_chars=min_section_chars,
                        max_section_chars=max_section_chars,
                    )
                )
                current_lines = []
            current_title = text
            continue

        current_lines.append(text)

    if current_lines:
        sections.extend(
            _split_content_into_sections(
                current_title,
                "\n".join(current_lines),
                min_section_chars=min_section_chars,
                max_section_chars=max_section_chars,
            )
        )

    if not sections:
        raw_text = "\n".join(line.text for line in lines)
        sections = _split_content_into_sections(
            "Section 1",
            raw_text,
            min_section_chars=min_section_chars,
            max_section_chars=max_section_chars,
        )

    return [section for section in sections if section.content.strip()]


def _extract_with_pymupdf(pdf_path: Path, job_id: str) -> tuple[list[ExtractedLine], int]:
    pymupdf = _load_dependency("pymupdf")
    lines: list[ExtractedLine] = []
    
    storage_dir = Path(settings.storage_path) / job_id
    storage_dir.mkdir(parents=True, exist_ok=True)

    with pymupdf.open(pdf_path) as document:
        page_count = document.page_count
        for page_index in range(page_count):
            page = document.load_page(page_index)
            
            for img in page.get_images(full=True):
                xref = img[0]
                try:
                    pix = pymupdf.Pixmap(document, xref)
                    if pix.n - pix.alpha > 3:
                        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                    img_name = f"img_p{page_index+1}_{xref}.png"
                    img_path = storage_dir / img_name
                    pix.save(str(img_path))
                    
                    lines.append(
                        ExtractedLine(
                            page_number=page_index + 1,
                            text=f"![Image_{xref}](/api/storage/{job_id}/{img_name})",
                            font_size=12.0,
                            is_bold=False,
                        )
                    )
                except Exception:
                    pass
            
            data = page.get_text("dict")
            for block in data.get("blocks", []):
                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    text = " ".join(span.get("text", "") for span in spans)
                    normalized = _normalize_line(text)
                    if not normalized:
                        continue

                    sizes = [float(span.get("size", 0.0)) for span in spans if span.get("size")]
                    font_size = sum(sizes) / len(sizes) if sizes else None
                    bold = any("bold" in str(span.get("font", "")).lower() for span in spans)

                    lines.append(
                        ExtractedLine(
                            page_number=page_index + 1,
                            text=normalized,
                            font_size=font_size,
                            is_bold=bold,
                        )
                    )

    return lines, page_count


def _extract_with_pdfplumber(pdf_path: Path) -> tuple[list[ExtractedLine], int]:
    pdfplumber = _load_dependency("pdfplumber")
    lines: list[ExtractedLine] = []

    with pdfplumber.open(pdf_path) as document:
        page_count = len(document.pages)
        for page_index, page in enumerate(document.pages, start=1):
            words = page.extract_words(
                use_text_flow=True,
                keep_blank_chars=False,
                extra_attrs=["size", "fontname"],
            )
            grouped: dict[int, list[dict]] = defaultdict(list)
            for word in words:
                line_key = int(float(word.get("top", 0.0)) // 3)
                grouped[line_key].append(word)

            for _, line_words in sorted(grouped.items(), key=lambda item: item[0]):
                sorted_words = sorted(line_words, key=lambda word: float(word.get("x0", 0.0)))
                text = _normalize_line(" ".join(str(word.get("text", "")) for word in sorted_words))
                if not text:
                    continue

                sizes = [float(word.get("size", 0.0)) for word in sorted_words if word.get("size")]
                font_size = sum(sizes) / len(sizes) if sizes else None
                bold = any("bold" in str(word.get("fontname", "")).lower() for word in sorted_words)

                lines.append(
                    ExtractedLine(
                        page_number=page_index,
                        text=text,
                        font_size=font_size,
                        is_bold=bold,
                    )
                )

    return lines, page_count


def _extract_with_ocr(pdf_path: Path) -> tuple[list[ExtractedLine], int]:
    pymupdf = _load_dependency("pymupdf")
    pytesseract = _load_dependency("pytesseract")
    lines: list[ExtractedLine] = []

    with pymupdf.open(pdf_path) as document:
        page_count = document.page_count
        for page_index in range(page_count):
            page = document.load_page(page_index)
            pix = page.get_pixmap(dpi=220)
            image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            grayscale = image.convert("L")

            text = pytesseract.image_to_string(grayscale, lang=settings.ocr_language)
            for raw_line in text.splitlines():
                normalized = _normalize_line(raw_line)
                if not normalized:
                    continue

                lines.append(
                    ExtractedLine(
                        page_number=page_index + 1,
                        text=normalized,
                        font_size=None,
                        is_bold=False,
                    )
                )

    return lines, page_count


def _normalize_line(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if compact in {"", "-", "_"}:
        return ""
    if len(compact) == 1 and not compact.isalnum():
        return ""
    return compact


def _text_score(lines: list[ExtractedLine]) -> int:
    return sum(len(line.text) for line in lines)


def _needs_ocr(lines: list[ExtractedLine], page_count: int) -> bool:
    if page_count <= 0:
        return True

    text_chars = _text_score(lines)
    min_chars = max(200, page_count * 130)
    min_lines = page_count * 3
    return text_chars < min_chars or len(lines) < min_lines


def _estimate_body_font_size(lines: list[ExtractedLine]) -> float | None:
    sizes = [line.font_size for line in lines if line.font_size is not None and line.font_size > 0]
    if not sizes:
        return None
    return median(sizes)


def _is_heading(text: str, line: ExtractedLine, body_font_size: float | None) -> bool:
    if len(text) < 3 or len(text) > 110:
        return False

    if text.endswith(":") and len(text.split()) <= 10:
        return True

    for pattern in HEADING_PATTERNS:
        if pattern.match(text):
            return True

    if line.is_bold and len(text.split()) <= 12:
        return True

    if body_font_size and line.font_size and line.font_size >= body_font_size * 1.18:
        return True

    return False


def _remove_noise_lines(lines: list[ExtractedLine], page_count: int) -> list[ExtractedLine]:
    if page_count < 3:
        return lines

    normalized_counts = Counter(
        line.text.lower()
        for line in lines
        if 0 < len(line.text) <= 80 and not line.text.strip().isdigit()
    )
    repeated_noise = {
        text
        for text, count in normalized_counts.items()
        if count >= max(3, int(page_count * 0.7))
    }

    return [line for line in lines if line.text.lower() not in repeated_noise]


def _split_content_into_sections(
    title: str,
    content: str,
    min_section_chars: int,
    max_section_chars: int,
) -> list[SectionDraft]:
    normalized_content = content.strip()
    if not normalized_content:
        return []

    if len(normalized_content) <= max_section_chars:
        return [SectionDraft(title=_clean_title(title), content=normalized_content)]

    paragraphs = [part.strip() for part in normalized_content.split("\n") if part.strip()]
    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for paragraph in paragraphs:
        paragraph_len = len(paragraph)
        projected = current_len + paragraph_len + 1
        should_wrap = projected > max_section_chars and current_len >= min_section_chars
        if should_wrap and current_parts:
            chunks.append("\n".join(current_parts).strip())
            current_parts = [paragraph]
            current_len = paragraph_len
            continue

        current_parts.append(paragraph)
        current_len = projected

    if current_parts:
        chunks.append("\n".join(current_parts).strip())

    if len(chunks) == 1:
        return [SectionDraft(title=_clean_title(title), content=chunks[0])]

    base_title = _clean_title(title)
    return [
        SectionDraft(title=f"{base_title} ({index + 1})", content=chunk)
        for index, chunk in enumerate(chunks)
    ]


def _clean_title(title: str) -> str:
    cleaned = _normalize_line(title)
    return cleaned[:255] if cleaned else "Section"


def _mark_job_failed(db: Session, job: ImportJob, reason: str) -> None:
    job.status = "failed"
    job.error_message = reason[:1000]
    db.commit()
