from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
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


def fetch_indeed(keyword: str, location: str, max_results: int, user_agent: str) -> list[dict[str, Any]]:
    """Fetch jobs from Indeed RSS feed — no Playwright, no bot detection."""
    url = f"https://www.indeed.com/rss?q={quote_plus(keyword)}&l={quote_plus(location)}"
    jobs: list[dict[str, Any]] = []

    try:
        req = Request(url, headers={"User-Agent": user_agent})
        with urlopen(req, timeout=30) as resp:
            content = resp.read()
        root = ET.fromstring(content)
        channel = root.find("channel")
        if channel is None:
            return jobs
        for item in channel.findall("item")[:max_results]:
            title_el = item.find("title")
            link_el = item.find("link")
            guid_el = item.find("guid")
            if title_el is None:
                continue
            title_text = (title_el.text or "").strip()
            # In RSS 2.0 <link> is a text node; fall back to <guid>
            job_url = (link_el.text or "").strip() if link_el is not None else ""
            if not job_url and guid_el is not None:
                job_url = (guid_el.text or "").strip()
            if not job_url:
                continue
            ext_id = job_url.split("jk=")[-1].split("&")[0] if "jk=" in job_url else job_url
            jobs.append(
                {
                    "source": "Indeed",
                    "external_id": ext_id,
                    "title": title_text,
                    "company": None,
                    "location": location,
                    "job_url": job_url,
                    "search_keyword": keyword,
                    "discovered_at": utc_now(),
                }
            )
    except Exception as exc:
        logger.warning("Indeed RSS fetch failed for %s: %s", keyword, exc)

    return jobs


def fetch_craigslist(page: Page, keyword: str, region: str, max_results: int) -> list[dict[str, Any]]:
    url = f"https://{region}.craigslist.org/search/jjj?query={quote_plus(keyword)}"
    jobs: list[dict[str, Any]] = []

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(1200)
        links = page.locator("a.posting-title")
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


def fetch_weworkremotely(keyword: str, max_results: int, user_agent: str) -> list[dict[str, Any]]:
    """Fetch jobs from We Work Remotely public RSS feed, filtered by keyword."""
    url = "https://weworkremotely.com/remote-jobs.rss"
    jobs: list[dict[str, Any]] = []
    keyword_lower = keyword.lower()

    try:
        req = Request(url, headers={"User-Agent": user_agent})
        with urlopen(req, timeout=30) as resp:
            content = resp.read()
        root = ET.fromstring(content)
        channel = root.find("channel")
        if channel is None:
            return jobs
        for item in channel.findall("item"):
            title_el = item.find("title")
            link_el = item.find("link")
            guid_el = item.find("guid")
            desc_el = item.find("description")
            if title_el is None:
                continue
            title_text = (title_el.text or "").strip()
            haystack = (title_text + " " + (desc_el.text or "")).lower()
            if keyword_lower not in haystack:
                continue
            job_url = (link_el.text or "").strip() if link_el is not None else ""
            if not job_url and guid_el is not None:
                job_url = (guid_el.text or "").strip()
            if not job_url:
                continue
            description = BeautifulSoup(desc_el.text or "", "html.parser").get_text(" ", strip=True) if desc_el is not None else ""
            # Title often is "Company: Job Title"
            company = None
            if ": " in title_text:
                company, title_text = title_text.split(": ", 1)
            jobs.append(
                {
                    "source": "WeWorkRemotely",
                    "external_id": job_url.rstrip("/").split("/")[-1],
                    "title": title_text,
                    "company": company,
                    "location": "Remote",
                    "job_url": job_url,
                    "description": description[:5000],
                    "raw_text": description[:25000],
                    "search_keyword": keyword,
                    "discovered_at": utc_now(),
                }
            )
            if len(jobs) >= max_results:
                break
    except Exception as exc:
        logger.warning("WeWorkRemotely RSS fetch failed for %s: %s", keyword, exc)

    return jobs


def fetch_linkedin(keyword: str, max_results: int, user_agent: str) -> list[dict[str, Any]]:
    """Fetch jobs from LinkedIn public guest API (no auth, no Playwright)."""
    url = (
        "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
        f"?keywords={quote_plus(keyword)}&start=0&count={max_results}"
    )
    jobs: list[dict[str, Any]] = []

    try:
        req = Request(url, headers={"User-Agent": user_agent})
        with urlopen(req, timeout=30) as resp:
            html_content = resp.read().decode("utf-8", errors="replace")
        soup = BeautifulSoup(html_content, "html.parser")
        cards = soup.find_all("li")
        for card in cards[:max_results]:
            link_el = card.find("a", class_="base-card__full-link") or card.find("a", href=True)
            title_el = card.find("h3")
            company_el = card.find("h4")
            location_el = card.find("span", class_=lambda c: c and "location" in c)
            if not link_el or not title_el:
                continue
            job_url = (link_el.get("href") or "").strip().split("?")[0]
            if not job_url:
                continue
            title_text = title_el.get_text(strip=True)
            company = company_el.get_text(strip=True) if company_el else None
            location = location_el.get_text(strip=True) if location_el else "Remote"
            ext_id = job_url.rstrip("/").split("/")[-1]
            jobs.append(
                {
                    "source": "LinkedIn",
                    "external_id": ext_id,
                    "title": title_text,
                    "company": company,
                    "location": location,
                    "job_url": job_url,
                    "search_keyword": keyword,
                    "discovered_at": utc_now(),
                }
            )
    except Exception as exc:
        logger.warning("LinkedIn fetch failed for %s: %s", keyword, exc)

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

    # --- RSS / HTTP sources (no Playwright) ---
    for keyword in source_queries.get("indeed", []):
        collected.extend(fetch_indeed(keyword, settings.indeed_location, settings.max_results_per_query, settings.user_agent))

    for keyword in source_queries.get("remote", []):
        collected.extend(fetch_remoteok(keyword, settings.max_results_per_query, settings.user_agent))

    for keyword in source_queries.get("weworkremotely", []):
        collected.extend(fetch_weworkremotely(keyword, settings.max_results_per_query, settings.user_agent))

    for keyword in source_queries.get("linkedin", []):
        collected.extend(fetch_linkedin(keyword, settings.max_results_per_query, settings.user_agent))

    # --- Playwright sources ---
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=settings.headless)
        context = browser.new_context(user_agent=settings.user_agent)
        page = context.new_page()

        for keyword in source_queries.get("craigslist", []):
            collected.extend(fetch_craigslist(page, keyword, settings.craigslist_region, settings.max_results_per_query))

        browser.close()

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