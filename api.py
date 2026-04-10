"""
FastAPI dashboard backend for ResumeBot.
Wraps existing app.* modules without modifying them.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import threading
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, Body, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

# ---------------------------------------------------------------------------
# Lazy settings helper — returns None if env is not fully configured
# ---------------------------------------------------------------------------

def _try_get_settings():
    try:
        from app.config import get_settings
        return get_settings()
    except Exception as exc:
        return exc


def _require_settings():
    result = _try_get_settings()
    if isinstance(result, Exception):
        raise HTTPException(
            status_code=503,
            detail=f"Configuration error: {result}. Check your .env file.",
        )
    return result


# ---------------------------------------------------------------------------
# Scraper state (module-level, single process)
# ---------------------------------------------------------------------------

_scraper_lock = threading.Lock()
_scraper_state: dict[str, Any] = {"running": False, "last_result": None, "last_error": None}

# ---------------------------------------------------------------------------
# Lead enrichment state (module-level, single process)
# ---------------------------------------------------------------------------

_enrich_lock = threading.Lock()
_enrich_state: dict[str, Any] = {
    "running": False,
    "total": 0,
    "completed": 0,
    "last_error": None,
}


def _get_db_path() -> Path:
    """Return database path even if full settings fail."""
    try:
        return _require_settings().database_path
    except HTTPException:
        fallback = Path(os.getenv("DATABASE_PATH", "./data/resumebot.sqlite3")).expanduser().resolve()
        fallback.parent.mkdir(parents=True, exist_ok=True)
        return fallback


def _ensure_db():
    from app.db import init_db
    init_db(_get_db_path())


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="ResumeBot Dashboard API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    try:
        _ensure_db()
        from app.db import init_leads_db
        init_leads_db(_get_db_path())
    except Exception as exc:
        print(f"[startup] DB init skipped: {exc}")


# ---------------------------------------------------------------------------
# Helper: row → dict
# ---------------------------------------------------------------------------

def _row_to_dict(row) -> dict:
    if row is None:
        return {}
    if hasattr(row, "keys"):
        return dict(row)
    return dict(row)


# ---------------------------------------------------------------------------
# POST /api/scrape
# ---------------------------------------------------------------------------

def _run_scrape():
    """Blocking scrape — runs in a thread."""
    global _scraper_state
    try:
        from app.config import get_settings
        from app.db import upsert_job, init_db
        from app.job_sources import collect_jobs
        from app.resume_intel import build_resume_profile
        from app.telegram_bot import configured_queries

        settings = get_settings()
        init_db(settings.database_path)
        profile = build_resume_profile(settings.resume_path, configured_queries(settings))
        jobs = collect_jobs(settings, profile["source_queries"])

        created = 0
        for job in jobs:
            _, is_new = upsert_job(settings.database_path, job)
            if is_new:
                created += 1

        _scraper_state["last_result"] = {"jobs_found": len(jobs), "new": created}
        _scraper_state["last_error"] = None
    except Exception as exc:
        _scraper_state["last_error"] = str(exc)
        _scraper_state["last_result"] = None
    finally:
        _scraper_state["running"] = False


@app.post("/api/scrape")
async def trigger_scrape():
    with _scraper_lock:
        if _scraper_state["running"]:
            return JSONResponse({"status": "already_running"}, status_code=202)
        _scraper_state["running"] = True

    thread = threading.Thread(target=_run_scrape, daemon=True)
    thread.start()
    return {"status": "started"}


@app.get("/api/scrape/status")
async def scrape_status():
    return {
        "running": _scraper_state["running"],
        "last_result": _scraper_state["last_result"],
        "last_error": _scraper_state["last_error"],
    }


# ---------------------------------------------------------------------------
# GET /api/jobs
# ---------------------------------------------------------------------------

@app.get("/api/jobs")
async def get_jobs(status: str | None = Query(default=None)):
    from app.db import list_jobs
    db = _get_db_path()
    _ensure_db()
    rows = list_jobs(db, status=status, limit=500)
    return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# POST /api/jobs/{id}/approve
# ---------------------------------------------------------------------------

@app.post("/api/jobs/{job_id}/approve")
async def approve_job(job_id: int, background_tasks: BackgroundTasks):
    settings = _require_settings()
    from app.db import get_job, update_job_status, save_packet, init_db
    from app.resume_intel import build_resume_profile
    from app.tailoring import create_packet
    from app.telegram_bot import configured_queries

    init_db(settings.database_path)
    job = get_job(settings.database_path, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job #{job_id} not found")

    def _build():
        try:
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
        except Exception as exc:
            print(f"[approve] packet build failed for job {job_id}: {exc}")

    background_tasks.add_task(_build)
    return {"status": "packet_building", "job_id": job_id}


# ---------------------------------------------------------------------------
# POST /api/jobs/{id}/trash
# ---------------------------------------------------------------------------

@app.post("/api/jobs/{job_id}/trash")
async def trash_job(job_id: int):
    from app.db import update_job_status
    db = _get_db_path()
    _ensure_db()
    update_job_status(db, job_id, "trash")
    return {"status": "trashed", "job_id": job_id}


# ---------------------------------------------------------------------------
# POST /api/jobs/{id}/save
# ---------------------------------------------------------------------------

@app.post("/api/jobs/{job_id}/save")
async def save_job(job_id: int):
    from app.db import update_job_status
    db = _get_db_path()
    _ensure_db()
    update_job_status(db, job_id, "saved")
    return {"status": "saved", "job_id": job_id}


# ---------------------------------------------------------------------------
# GET /api/jobs/{id}/packet
# ---------------------------------------------------------------------------

@app.get("/api/jobs/{job_id}/packet")
async def get_job_packet(job_id: int):
    from app.db import get_packet, get_job
    db = _get_db_path()
    _ensure_db()
    job = get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job #{job_id} not found")
    packet = get_packet(db, job_id)
    if packet is None:
        raise HTTPException(status_code=404, detail=f"No packet for job #{job_id} yet")
    return {**_row_to_dict(job), "packet": _row_to_dict(packet)}


# ---------------------------------------------------------------------------
# POST /api/jobs/{id}/send
# ---------------------------------------------------------------------------

@app.post("/api/jobs/{job_id}/send")
async def send_job(job_id: int):
    settings = _require_settings()
    from app.db import get_job, get_packet, update_job_status, update_packet_status, record_event, init_db
    from app.mailer import send_application

    init_db(settings.database_path)
    job = get_job(settings.database_path, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job #{job_id} not found")
    if not job["contact_email"]:
        raise HTTPException(status_code=422, detail="No contact email found for this job")

    packet = get_packet(settings.database_path, job_id)
    if packet is None:
        raise HTTPException(status_code=422, detail=f"No packet for job #{job_id}. Approve first.")

    payload = {
        "resume_output_path": packet["resume_output_path"],
        "cover_letter_path": packet["cover_letter_path"],
        "cover_letter_text": packet["cover_letter_text"],
    }

    try:
        await asyncio.to_thread(send_application, settings, dict(job), payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Send failed: {exc}")

    update_job_status(settings.database_path, job_id, "applied")
    update_packet_status(settings.database_path, job_id, "sent")
    record_event(settings.database_path, "application_sent", job["contact_email"], job_id)

    return {"status": "sent", "job_id": job_id, "recipient": job["contact_email"]}


# ---------------------------------------------------------------------------
# GET /api/stats
# ---------------------------------------------------------------------------

@app.get("/api/stats")
async def get_stats():
    from app.db import stats
    db = _get_db_path()
    _ensure_db()
    payload = stats(db)
    payload["scraper_running"] = _scraper_state["running"]
    return payload


# ---------------------------------------------------------------------------
# POST /api/resume  (file upload)
# ---------------------------------------------------------------------------

@app.post("/api/resume")
async def upload_resume(file: UploadFile = File(...)):
    allowed = {".txt", ".pdf", ".docx"}
    suffix = Path(file.filename or "resume.txt").suffix.lower()
    if suffix not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}. Use txt, pdf, or docx.")

    # Determine where to save
    try:
        settings = _require_settings()
        dest = settings.resume_path.parent / f"resume{suffix}"
    except HTTPException:
        dest = Path(os.getenv("RESUME_PATH", f"./resume{suffix}")).expanduser().resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)

    contents = await file.read()
    dest.write_bytes(contents)

    # Bust settings cache so next call re-reads RESUME_PATH
    try:
        from app.config import get_settings
        get_settings.cache_clear()
    except Exception:
        pass

    return {"status": "uploaded", "path": str(dest), "filename": file.filename}


# ---------------------------------------------------------------------------
# GET /api/resume  (current resume info)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# POST /api/leads/parse   — preview only, no DB write
# ---------------------------------------------------------------------------

@app.post("/api/leads/parse")
async def parse_leads_preview(body: dict = Body(...)):
    from app.lead_enrichment import parse_tsv_leads
    tsv = body.get("tsv", "")
    if not tsv.strip():
        return []
    return parse_tsv_leads(tsv)


# ---------------------------------------------------------------------------
# POST /api/leads/enrich  — store leads + kick off enrichment thread
# ---------------------------------------------------------------------------

@app.post("/api/leads/enrich")
async def start_enrichment(body: dict = Body(...)):
    from app.lead_enrichment import (
        parse_tsv_leads,
        search_company_website,
        crawl_for_contact,
        validate_email_mx,
        random_delay,
        USER_AGENT,
    )
    from app.db import (
        init_leads_db, insert_lead, clear_leads,
        get_lead, update_lead,
    )
    from playwright.sync_api import sync_playwright

    tsv = body.get("tsv", "")
    if not tsv.strip():
        raise HTTPException(status_code=400, detail="No TSV data provided")

    db = _get_db_path()
    init_leads_db(db)

    leads = parse_tsv_leads(tsv)
    if not leads:
        raise HTTPException(status_code=400, detail="No valid leads found in input")

    with _enrich_lock:
        if _enrich_state["running"]:
            return JSONResponse({"status": "already_running"}, status_code=202)

    # Wipe previous batch and insert fresh
    clear_leads(db)
    lead_ids: list[int] = [insert_lead(db, lead) for lead in leads]

    with _enrich_lock:
        _enrich_state.update({
            "running": True,
            "total": len(lead_ids),
            "completed": 0,
            "last_error": None,
        })

    def _run():
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                ctx = browser.new_context(
                    user_agent=USER_AGENT,
                    viewport={"width": 1280, "height": 800},
                    extra_http_headers={
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                    },
                )
                page = ctx.new_page()
                # Basic stealth: mask navigator.webdriver
                page.add_init_script(
                    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
                    "window.chrome={runtime:{}};"
                )

                for lead_id in lead_ids:
                    try:
                        row = get_lead(db, lead_id)
                        if row is None:
                            continue
                        lead = dict(row)
                        update_lead(db, lead_id, status="in_progress")

                        updates: dict = {}

                        # Step 1: find website
                        random_delay(0.8, 2.0)
                        website = search_company_website(
                            lead["company"],
                            lead.get("city", ""),
                            lead.get("state", ""),
                            page,
                        )

                        if website:
                            updates["website"] = website

                            # Step 2: crawl for email + contact
                            random_delay(1.5, 3.5)
                            contact = crawl_for_contact(website, page)

                            if contact["email"]:
                                mx_ok = validate_email_mx(contact["email"])
                                updates["email"] = contact["email"]
                                base_conf = contact["confidence"]
                                updates["confidence"] = base_conf if mx_ok else max(base_conf - 20, 0)

                            if contact["contact_name"]:
                                updates["contact_name"] = contact["contact_name"]

                            updates["status"] = "found" if contact.get("email") else "not_found"
                        else:
                            updates["status"] = "not_found"

                        update_lead(db, lead_id, **updates)

                    except Exception as exc:
                        _enrich_state["last_error"] = str(exc)
                        try:
                            update_lead(db, lead_id, status="not_found", error=str(exc)[:500])
                        except Exception:
                            pass
                    finally:
                        with _enrich_lock:
                            _enrich_state["completed"] += 1

                browser.close()
        finally:
            with _enrich_lock:
                _enrich_state["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return {"status": "started", "total": len(lead_ids)}


# ---------------------------------------------------------------------------
# GET /api/leads
# ---------------------------------------------------------------------------

@app.get("/api/leads")
async def get_leads(status: str | None = Query(default=None)):
    from app.db import list_leads, init_leads_db
    db = _get_db_path()
    init_leads_db(db)
    rows = list_leads(db, status=status)
    return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# GET /api/leads/enrich/status
# ---------------------------------------------------------------------------

@app.get("/api/leads/enrich/status")
async def enrichment_status():
    from app.db import lead_stats, init_leads_db
    db = _get_db_path()
    init_leads_db(db)
    counts = lead_stats(db)
    return {
        **counts,
        "enriching": _enrich_state["running"],
        "progress_total": _enrich_state["total"],
        "progress_completed": _enrich_state["completed"],
        "last_error": _enrich_state["last_error"],
    }


# ---------------------------------------------------------------------------
# GET /api/leads/export  — CSV download
# ---------------------------------------------------------------------------

@app.get("/api/leads/export")
async def export_leads_csv():
    import csv
    import io
    from app.db import list_leads, init_leads_db

    db = _get_db_path()
    init_leads_db(db)
    rows = list_leads(db)

    buf = io.StringIO()
    fieldnames = [
        "id", "company", "city", "state", "phone",
        "website", "email", "contact_name", "confidence",
        "status", "ambiguous",
    ]
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(dict(row))

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads_enriched.csv"},
    )


# ---------------------------------------------------------------------------
# DELETE /api/leads  — clear all leads
# ---------------------------------------------------------------------------

@app.delete("/api/leads")
async def delete_all_leads():
    from app.db import clear_leads, init_leads_db
    db = _get_db_path()
    init_leads_db(db)
    clear_leads(db)
    with _enrich_lock:
        _enrich_state.update({"running": False, "total": 0, "completed": 0, "last_error": None})
    return {"status": "cleared"}


# ---------------------------------------------------------------------------
# GET /api/resume  (current resume info)
# ---------------------------------------------------------------------------

@app.get("/api/resume")
async def get_resume_info():
    try:
        settings = _require_settings()
        path = settings.resume_path
        return {
            "path": str(path),
            "filename": path.name,
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else 0,
        }
    except HTTPException:
        resume_path_env = os.getenv("RESUME_PATH", "")
        return {
            "path": resume_path_env,
            "filename": Path(resume_path_env).name if resume_path_env else "",
            "exists": False,
            "size_bytes": 0,
            "warning": "Settings not fully configured",
        }
