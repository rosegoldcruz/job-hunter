from __future__ import annotations

import asyncio
import html
import logging
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from app.db import (
    get_job,
    get_packet,
    init_db,
    list_jobs,
    record_event,
    save_packet,
    set_job_message_id,
    stats,
    update_job_status,
    update_packet_status,
    upsert_job,
)
from app.job_sources import collect_jobs
from app.resume_intel import build_resume_profile
from app.tailoring import create_packet
from app.mailer import send_application


logger = logging.getLogger(__name__)


def build_job_keyboard(job_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Approve", callback_data=f"review:approve:{job_id}"),
                InlineKeyboardButton("Save", callback_data=f"review:save:{job_id}"),
                InlineKeyboardButton("Trash", callback_data=f"review:trash:{job_id}"),
            ]
        ]
    )


def build_final_keyboard(job_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Final Send", callback_data=f"final:send:{job_id}"),
                InlineKeyboardButton("Hold", callback_data=f"final:hold:{job_id}"),
            ]
        ]
    )


def render_job_card(job) -> str:
    title = html.escape(job["title"])
    company = html.escape(job["company"] or "Unknown company")
    location = html.escape(job["location"] or "Unknown location")
    source = html.escape(job["source"])
    keyword = html.escape(job["search_keyword"] or "")
    url = html.escape(job["job_url"])

    return (
        f"<b>{title}</b>\n"
        f"Company: {company}\n"
        f"Location: {location}\n"
        f"Source: {source}\n"
        f"Keyword: {keyword}\n"
        f"URL: {url}"
    )


def configured_queries(settings) -> dict[str, list[str]]:
    return {
        "indeed": settings.indeed_keywords,
        "linkedin": settings.linkedin_keywords,
        "craigslist": settings.craigslist_keywords,
        "remote": settings.remote_keywords,
        "weworkremotely": settings.weworkremotely_keywords,
    }


async def queue_new_jobs(application: Application, settings) -> int:
    profile = build_resume_profile(settings.resume_path, configured_queries(settings))
    collected = await asyncio.to_thread(collect_jobs, settings, profile["source_queries"])

    new_count = 0
    for job in collected:
        job_id, created = upsert_job(settings.database_path, job)
        if not created:
            continue

        stored = get_job(settings.database_path, job_id)
        if stored is None:
            continue

        message = await application.bot.send_message(
            chat_id=settings.telegram_chat_id,
            text=render_job_card(stored),
            parse_mode=ParseMode.HTML,
            reply_markup=build_job_keyboard(job_id),
            disable_web_page_preview=True,
        )
        set_job_message_id(settings.database_path, job_id, message.message_id)
        record_event(settings.database_path, "job_queued", "telegram_message_sent", job_id)
        new_count += 1

    return new_count


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    text = (
        "ResumeBot is live.\n\n"
        "Commands:\n"
        "/sync - fetch fresh jobs\n"
        "/queue - show pending jobs\n"
        "/stats - show counts\n\n"
        f"Database: {settings.database_path}"
    )
    await update.effective_message.reply_text(text)


async def sync_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    await update.effective_message.reply_text("Syncing jobs now...")
    new_count = await queue_new_jobs(context.application, settings)
    await update.effective_message.reply_text(f"Sync complete. New jobs queued: {new_count}")


async def queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    jobs = list_jobs(settings.database_path, status="new", limit=10)
    if not jobs:
        await update.effective_message.reply_text("No pending jobs in the new queue.")
        return

    for job in jobs:
        await update.effective_message.reply_text(
            render_job_card(job),
            parse_mode=ParseMode.HTML,
            reply_markup=build_job_keyboard(int(job["id"])),
            disable_web_page_preview=True,
        )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    payload = stats(settings.database_path)
    text = (
        f"new: {payload['new']}\n"
        f"saved: {payload['saved']}\n"
        f"approved: {payload['approved']}\n"
        f"trash: {payload['trash']}\n"
        f"applied: {payload['applied']}\n"
        f"manual_followup: {payload['manual_followup']}"
    )
    await update.effective_message.reply_text(text)


async def review_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    profile = context.application.bot_data["resume_profile"]
    query = update.callback_query
    await query.answer()

    _, action, job_id_raw = (query.data or "").split(":", 2)
    job_id = int(job_id_raw)
    job = get_job(settings.database_path, job_id)
    if job is None:
        await query.edit_message_text("Job no longer exists in the database.")
        return

    if action == "save":
        update_job_status(settings.database_path, job_id, "saved")
        record_event(settings.database_path, "job_saved", "saved from telegram", job_id)
        await query.edit_message_text(f"Saved job #{job_id}.\n\n{job['title']}")
        return

    if action == "trash":
        update_job_status(settings.database_path, job_id, "trash")
        record_event(settings.database_path, "job_trash", "trashed from telegram", job_id)
        await query.edit_message_text(f"Trashed job #{job_id}.\n\n{job['title']}")
        return

    if action == "approve":
        update_job_status(settings.database_path, job_id, "approved")
        packet = create_packet(settings, dict(job), profile)
        save_packet(
            settings.database_path,
            job_id,
            packet["resume_output_path"],
            packet["cover_letter_path"],
            packet["cover_letter_text"],
        )
        record_event(settings.database_path, "job_approved", "packet_built", job_id)

        await query.edit_message_text(f"Approved job #{job_id}. Packet built for final approval.")

        resume_path = Path(packet["resume_output_path"])
        with resume_path.open("rb") as fh:
            await context.application.bot.send_document(
                chat_id=settings.telegram_chat_id,
                document=fh,
                caption=f"Tailored resume for job #{job_id}: {job['title']}",
            )

        cover_text = html.escape(packet["cover_letter_text"])
        await context.application.bot.send_message(
            chat_id=settings.telegram_chat_id,
            text=(
                f"<b>Final Approval - Job #{job_id}</b>\n"
                f"{html.escape(job['title'])}\n"
                f"Company: {html.escape(job['company'] or 'Unknown')}\n"
                f"Recipient: {html.escape(job['contact_email'] or 'No contact email found')}\n\n"
                f"<pre>{cover_text}</pre>"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=build_final_keyboard(job_id),
        )


async def final_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    query = update.callback_query
    await query.answer()

    _, action, job_id_raw = (query.data or "").split(":", 2)
    job_id = int(job_id_raw)
    job = get_job(settings.database_path, job_id)
    packet = get_packet(settings.database_path, job_id)

    if job is None or packet is None:
        await query.edit_message_text("Job or packet missing. Cannot continue.")
        return

    if action == "hold":
        update_packet_status(settings.database_path, job_id, "hold")
        record_event(settings.database_path, "final_hold", "held from telegram", job_id)
        await query.edit_message_text(f"Held job #{job_id} for later.")
        return

    if not job["contact_email"]:
        update_job_status(settings.database_path, job_id, "manual_followup", "Missing recruiter email.")
        update_packet_status(settings.database_path, job_id, "manual_followup")
        record_event(settings.database_path, "manual_followup", "missing recipient email", job_id)
        await query.edit_message_text(
            "No recruiter email was found on the posting. Marked as manual_followup instead of blind sending."
        )
        return

    send_payload = {
        "resume_output_path": packet["resume_output_path"],
        "cover_letter_path": packet["cover_letter_path"],
        "cover_letter_text": packet["cover_letter_text"],
    }

    await asyncio.to_thread(send_application, settings, dict(job), send_payload)
    update_job_status(settings.database_path, job_id, "applied")
    update_packet_status(settings.database_path, job_id, "sent")
    record_event(settings.database_path, "application_sent", job["contact_email"], job_id)
    await query.edit_message_text(
        f"Application sent for job #{job_id} to {job['contact_email']}."
    )


def build_application(settings) -> Application:
    init_db(settings.database_path)
    application = Application.builder().token(settings.telegram_bot_token).build()
    application.bot_data["settings"] = settings
    application.bot_data["resume_profile"] = build_resume_profile(settings.resume_path, configured_queries(settings))

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("sync", sync_command))
    application.add_handler(CommandHandler("queue", queue_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CallbackQueryHandler(review_callback, pattern=r"^review:"))
    application.add_handler(CallbackQueryHandler(final_callback, pattern=r"^final:"))
    return application