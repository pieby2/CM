import argparse
import logging
from time import sleep

from sqlalchemy import select

from app.database import SessionLocal
from app.models import ImportJob
from app.services.pdf_pipeline import PDFProcessingError, process_import_job

logger = logging.getLogger("cue.pdf_worker")


def process_next_job() -> bool:
    with SessionLocal() as db:
        stmt = select(ImportJob.id).where(ImportJob.status == "queued").order_by(ImportJob.created_at.asc()).limit(1)
        job_id = db.execute(stmt).scalar_one_or_none()

        if job_id is None:
            return False

        try:
            result = process_import_job(db, job_id)
            logger.info(
                "processed job=%s method=%s pages=%s sections=%s chars=%s",
                result.job_id,
                result.extraction_method,
                result.page_count,
                result.section_count,
                result.extracted_char_count,
            )
        except PDFProcessingError as exc:
            logger.error("failed job=%s reason=%s", job_id, exc)
        except Exception:
            logger.exception("unexpected worker failure for job=%s", job_id)

        return True


def run_worker(poll_seconds: float, once: bool) -> None:
    while True:
        had_job = process_next_job()
        if once:
            return

        if not had_job:
            sleep(max(0.5, poll_seconds))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process queued PDF import jobs")
    parser.add_argument("--once", action="store_true", help="Process at most one queued job and exit")
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=5.0,
        help="Polling delay in seconds when running as a loop",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    run_worker(poll_seconds=args.poll_seconds, once=args.once)


if __name__ == "__main__":
    main()
