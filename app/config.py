from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


TRUE_VALUES = {"1", "true", "yes", "on", "y"}


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES


def _as_csv(value: str | None, default: str = "") -> list[str]:
    source = value if value is not None else default
    return [item.strip() for item in source.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_chat_id: int
    email_host: str
    email_port: int
    email_use_tls: bool
    email_user: str
    email_password: str
    candidate_name: str
    candidate_email: str
    candidate_phone: str
    candidate_city: str
    resume_path: Path
    database_path: Path
    output_dir: Path
    headless: bool
    indeed_location: str
    craigslist_region: str
    max_results_per_query: int
    indeed_keywords: list[str]
    linkedin_keywords: list[str]
    craigslist_keywords: list[str]
    remote_keywords: list[str]
    user_agent: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()

    settings = Settings(
        telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"].strip(),
        telegram_chat_id=int(os.environ["TELEGRAM_CHAT_ID"].strip()),
        email_host=os.getenv("EMAIL_HOST", "smtp.gmail.com").strip(),
        email_port=int(os.getenv("EMAIL_PORT", "587").strip()),
        email_use_tls=_as_bool(os.getenv("EMAIL_USE_TLS", "true"), True),
        email_user=os.environ["EMAIL_USER"].strip(),
        email_password=os.environ["EMAIL_PASSWORD"].strip(),
        candidate_name=os.getenv("CANDIDATE_NAME", "Candidate").strip(),
        candidate_email=os.getenv("CANDIDATE_EMAIL", "candidate@example.com").strip(),
        candidate_phone=os.getenv("CANDIDATE_PHONE", "").strip(),
        candidate_city=os.getenv("CANDIDATE_CITY", "").strip(),
        resume_path=Path(os.environ["RESUME_PATH"]).expanduser().resolve(),
        database_path=Path(os.getenv("DATABASE_PATH", "./data/resumebot.sqlite3")).expanduser().resolve(),
        output_dir=Path(os.getenv("OUTPUT_DIR", "./output")).expanduser().resolve(),
        headless=_as_bool(os.getenv("HEADLESS", "true"), True),
        indeed_location=os.getenv("INDEED_LOCATION", "Remote").strip(),
        craigslist_region=os.getenv("CRAIGSLIST_REGION", "phoenix").strip(),
        max_results_per_query=int(os.getenv("MAX_RESULTS_PER_QUERY", "5").strip()),
        indeed_keywords=_as_csv(
            os.getenv("INDEED_KEYWORDS"),
            "crm automation,marketing automation,revenue operations,revops,sales automation,pipeline automation,python backend,next.js developer,typescript,full stack developer,api development,lead routing,conversion tracking",
        ),
        linkedin_keywords=_as_csv(
            os.getenv("LINKEDIN_KEYWORDS"),
            "revenue operations,revops,solutions engineer,automation engineer,crm automation,marketing automation,integrations engineer,full stack developer,next.js developer,python engineer,technical operations",
        ),
        craigslist_keywords=_as_csv(
            os.getenv("CRAIGSLIST_KEYWORDS"),
            "crm,automation,funnels,pipeline,sales,marketing,website,web developer,frontend,backend,full stack,python,react,next.js,typescript,seo,ads,lead generation,telephony,voip,sms,a2p,twilio,asterisk",
        ),
        remote_keywords=_as_csv(
            os.getenv("REMOTE_KEYWORDS"),
            "python,api development,automation engineer,full stack developer,next.js,react,typescript,crm automation,marketing automation,solutions engineer",
        ),
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/138.0.0.0 Safari/537.36"
        ),
    )

    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    settings.output_dir.mkdir(parents=True, exist_ok=True)

    if not settings.resume_path.exists():
        raise FileNotFoundError(f"Resume file not found: {settings.resume_path}")

    return settings