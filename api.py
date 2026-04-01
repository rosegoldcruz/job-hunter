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

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
