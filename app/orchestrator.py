from __future__ import annotations

import argparse
import logging

from app.config import get_settings
from app.db import get_job, get_packet, init_db, save_packet, stats, update_job_status, update_packet_status, upsert_job
from app.job_sources import collect_jobs
from app.resume_intel import build_resume_profile
from app.tailoring import create_packet
from app.telegram_bot import build_application, configured_queries
from app.mailer import send_application


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


def cmd_sync() -> None:
    settings = get_settings()
    init_db(settings.database_path)
    profile = build_resume_profile(settings.resume_path, configured_queries(settings))
    jobs = collect_jobs(settings, profile["source_queries"])

    created = 0
    updated = 0
    for job in jobs:
        _, is_new = upsert_job(settings.database_path, job)
        if is_new:
            created += 1
        else:
            updated += 1

    payload = stats(settings.database_path)
    logger.info("Sync complete | created=%s updated=%s queue=%s", created, updated, payload)


def cmd_packet(job_id: int) -> None:
    settings = get_settings()
    init_db(settings.database_path)
    job = get_job(settings.database_path, job_id)
    if job is None:
        raise ValueError(f"Job #{job_id} not found")

    profile = build_resume_profile(settings.resume_path, configured_queries(settings))
    packet = create_packet(settings, dict(job), profile)
    save_packet(
        settings.database_path,
        job_id,
        packet["resume_output_path"],
        packet["cover_letter_path"],
        packet["cover_letter_text"],
    )
    update_job_status(settings.database_path, job_id, "approved")
    logger.info("Packet built for job %s", job_id)
    logger.info("Resume path: %s", packet["resume_output_path"])
    logger.info("Cover path: %s", packet["cover_letter_path"])


def cmd_apply(job_id: int) -> None:
    settings = get_settings()
    init_db(settings.database_path)
    job = get_job(settings.database_path, job_id)
    packet = get_packet(settings.database_path, job_id)
    if job is None:
        raise ValueError(f"Job #{job_id} not found")
    if packet is None:
        raise ValueError(f"Packet missing for job #{job_id}. Build it first.")
    if not job["contact_email"]:
        raise ValueError(f"Job #{job_id} has no contact email. Manual follow-up required.")

    payload = {
        "resume_output_path": packet["resume_output_path"],
        "cover_letter_path": packet["cover_letter_path"],
        "cover_letter_text": packet["cover_letter_text"],
    }
    send_application(settings, dict(job), payload)
    update_job_status(settings.database_path, job_id, "applied")
    update_packet_status(settings.database_path, job_id, "sent")
    logger.info("Application sent for job %s", job_id)


def cmd_bot() -> None:
    settings = get_settings()
    app = build_application(settings)
    logger.info("Starting Telegram bot...")
    app.run_polling(drop_pending_updates=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ResumeBot operator CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("sync", help="Scrape and store jobs")
    subparsers.add_parser("bot", help="Run Telegram bot")

    packet_parser = subparsers.add_parser("packet", help="Build packet for a job")
    packet_parser.add_argument("--job-id", type=int, required=True)

    apply_parser = subparsers.add_parser("apply", help="Send application for a job")
    apply_parser.add_argument("--job-id", type=int, required=True)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "sync":
        cmd_sync()
    elif args.command == "packet":
        cmd_packet(args.job_id)
    elif args.command == "apply":
        cmd_apply(args.job_id)
    elif args.command == "bot":
        cmd_bot()
    else:
        parser.error("Unknown command")


if __name__ == "__main__":
    main()