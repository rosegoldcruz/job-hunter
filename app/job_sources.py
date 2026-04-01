from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus, urljoin
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
from playwright.sync_api import Page, sync_playwright

from app.config import Settings


logger = logging.getLogger(__name__)
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def extract_contact_email(text: str) -> str | None:
    matches = EMAIL_RE.findall(text)
    for email in matches:
        lowered = email.lower()
        if "noreply" in lowered or "do-not-reply" in lowered:
            continue
        return email
    return None


def safe_inner_text(locator) -> str:
    try:
        text = locator.inner_text(timeout=1000) or ""
        return text.strip()
    except Exception:
        return ""


def safe_attr(locator, name: str) -> str:
    try:
        value = locator.get_attribute(name, timeout=1000)
        return (value or "").strip()
    except Exception:
        return ""


def enrich_detail(page: Page, job: dict[str, Any]) -> dict[str, Any]:
    try:
        page.goto(job["job_url"], wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(1200)
        text = page.locator("body").inner_text(timeout=2500)
        if text:
            job["raw_text"] = text[:25000]
            job["description"] = text[:5000]
            job["contact_email"] = job.get("contact_email") or extract_contact_email(text)
    except Exception as exc:
        logger.warning("Detail enrichment failed for %s: %s", job["job_url"], exc)
    return job


def fetch_indeed(page: Page, keyword: str, location: str, max_results: int) -> list[dict[str, Any]]:
    url = f"https://www.indeed.com/jobs?q={quote_plus(keyword)}&l={quote_plus(location)}"
    jobs: list[dict[str, Any]] = []
    seen: set[str] = set()

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(1500)
        links = page.locator("a[href*='/viewjob']")
        total = min(links.count(), max_results * 3)
        for idx in range(total):
            link = links.nth(idx)
            href = safe_attr(link, "href")
            title = safe_inner_text(link)
            if not href or not title:
                continue

            full_url = urljoin("https://www.indeed.com", href)
            if full_url in seen:
                continue
            seen.add(full_url)

            jobs.append(
                {
                    "source": "Indeed",
                    "external_id": full_url.split("jk=")[-1] if "jk=" in full_url else full_url,
                    "title": title,
                    "company": None,
                    "location": location,
                    "job_url": full_url,
                    "search_keyword": keyword,
                    "discovered_at": utc_now(),
                }
            )
            if len(jobs) >= max_results:
                break
    except Exception as exc:
        logger.warning("Indeed scrape failed for %s: %s", keyword, exc)

    return jobs


def fetch_craigslist(page: Page, keyword: str, region: str, max_results: int) -> list[dict[str, Any]]:
    url = f"https://{region}.craigslist.org/search/jjj?query={quote_plus(keyword)}"
    jobs: list[dict[str, Any]] = []

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(1200)
        links = page.locator("a.result-title")
        total = min(links.count(), max_results)
        for idx in range(total):
            link = links.nth(idx)
            href = safe_attr(link, "href")
            title = safe_inner_text(link)
            if not href or not title:
                continue
            jobs.append(
                {
                    "source": "Craigslist",
                    "external_id": href.rstrip("/").split("/")[-1],
                    "title": title,
                    "company": None,
                    "location": region,
                    "job_url": href,
                    "search_keyword": keyword,
                    "discovered_at": utc_now(),
                }
            )
    except Exception as exc:
        logger.warning("Craigslist scrape failed for %s: %s", keyword, exc)

    return jobs


def fetch_remoteok(keyword: str, max_results: int, user_agent: str) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []

    try:
        request = Request(
            "https://remoteok.com/api",
            headers={"User-Agent": user_agent},
        )
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))

        keyword_lower = keyword.lower()
        for item in payload:
            if not isinstance(item, dict):
                continue
            haystack = " ".join(
                [
                    str(item.get("position", "")),
                    str(item.get("company", "")),
                    str(item.get("description", "")),
                    " ".join(item.get("tags", []) or []),
                ]
            ).lower()
            if keyword_lower not in haystack:
                continue

            job_url = item.get("url") or item.get("apply_url")
            if not job_url:
                continue

            description = BeautifulSoup(item.get("description", ""), "html.parser").get_text(" ", strip=True)
            jobs.append(
                {
                    "source": "RemoteOK",
                    "external_id": str(item.get("id", job_url)),
                    "title": item.get("position") or "Untitled role",
                    "company": item.get("company"),
                    "location": item.get("location") or "Remote",
                    "job_url": job_url,
                    "description": description[:5000],
                    "raw_text": description[:25000],
                    "contact_email": extract_contact_email(str(item.get("description", ""))),
                    "search_keyword": keyword,
                    "discovered_at": utc_now(),
                }
            )
            if len(jobs) >= max_results:
                break
    except Exception as exc:
        logger.warning("RemoteOK fetch failed for %s: %s", keyword, exc)

    return jobs


def dedupe_jobs(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for job in jobs:
        key = job["job_url"].strip().lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(job)
    return deduped


def collect_jobs(settings: Settings, source_queries: dict[str, list[str]]) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=settings.headless)
        context = browser.new_context(user_agent=settings.user_agent)
        page = context.new_page()

        for keyword in source_queries.get("indeed", []):
            collected.extend(fetch_indeed(page, keyword, settings.indeed_location, settings.max_results_per_query))

        for keyword in source_queries.get("craigslist", []):
            collected.extend(fetch_craigslist(page, keyword, settings.craigslist_region, settings.max_results_per_query))

        if source_queries.get("linkedin"):
            logger.info(
                "LinkedIn keywords are configured, but the LinkedIn adapter is not implemented yet. Skipping %s keywords.",
                len(source_queries["linkedin"]),
            )

        browser.close()

    for keyword in source_queries.get("remote", []):
        collected.extend(fetch_remoteok(keyword, settings.max_results_per_query, settings.user_agent))

    unique_jobs = dedupe_jobs(collected)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=settings.headless)
        context = browser.new_context(user_agent=settings.user_agent)
        page = context.new_page()
        enriched: list[dict[str, Any]] = []
        for job in unique_jobs:
            enriched.append(enrich_detail(page, job))
        browser.close()

    return enriched