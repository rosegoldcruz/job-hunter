"""
Lead enrichment pipeline.

Reuses: extract_contact_email / EMAIL_RE from job_sources.py
New:    TSV parser, DuckDuckGo search, contact page crawler, MX validation,
        decision-maker name extraction.
"""
from __future__ import annotations

import logging
import random
import re
import time
from typing import Any
from urllib.parse import urljoin, urlparse, parse_qs, quote_plus

from bs4 import BeautifulSoup
from playwright.sync_api import Page

from app.job_sources import extract_contact_email

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/138.0.0.0 Safari/537.36"
)

CONTACT_PATHS = [
    "/contact",
    "/contact-us",
    "/about",
    "/about-us",
    "/team",
    "/staff",
    "/our-team",
    "/people",
]

# Domains to skip when evaluating search results
BAD_DOMAINS = [
    "duckduckgo", "google", "bing", "yahoo",
    "facebook", "instagram", "twitter", "x.com",
    "yelp", "yellowpages", "bbb.org", "linkedin",
    "indeed", "glassdoor", "wikipedia", "reddit",
    "youtube", "zillow", "trulia", "realtor.com",
    "apartments.com", "apartmentlist", "costar",
    "loopnet", "zoominfo", "hoovers", "dnb.com",
    "manta.com", "angieslist", "angi.com", "thumbtack",
    "homeadvisor", "houzz",
]

# Regex to detect an owner/decision-maker title near a name
DECISION_MAKER_RE = re.compile(
    r"([A-Z][a-z]+(?: [A-Z][a-z]+){1,2})"           # Proper-cased name (2-3 words)
    r"[\s,|•\-–—]*"
    r"(?:owner|founder|president|ceo|principal"
    r"|property\s+manager|general\s+manager"
    r"|broker|director|managing\s+member)",
    re.IGNORECASE,
)

# Junk substrings that disqualify an email
JUNK_EMAIL_SUBSTRINGS = [
    "noreply", "no-reply", "do-not-reply", "donotreply",
    "example.com", "test.com", "@domain", "placeholder",
    "your@", "email@email", "info@example",
]


# ---------------------------------------------------------------------------
# TSV / smashed-format parser
# ---------------------------------------------------------------------------

# Matches phone numbers like (408) 913-1082 / 408-913-1082 / 4089131082
PHONE_RE = re.compile(r"(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})")

# All-caps state-header pattern (e.g. "ARIZONA", "NEW MEXICO")
STATE_HEADER_RE = re.compile(r"^[A-Z][A-Z\s\-]{2,}$")


def _split_company_city(value: str) -> tuple[str, str, bool]:
    """
    Split "Company Name, City" on the last comma.
    Returns (company, city, ambiguous).
    ambiguous=True when there is no comma — city cannot be determined.
    """
    value = value.strip()
    if "," in value:
        idx = value.rfind(",")
        return value[:idx].strip(), value[idx + 1:].strip(), False
    return value, "", True


def _is_state_header(text: str) -> bool:
    return (
        bool(STATE_HEADER_RE.match(text))
        and not any(ch.isdigit() for ch in text)
    )


def _is_column_header(text: str) -> bool:
    return text.lower() in (
        "company", "business", "name", "company name",
        "company/city", "company + city",
    )


def parse_tsv_leads(tsv_text: str) -> list[dict[str, Any]]:
    """
    Auto-detect format and parse into a list of lead dicts.

    FORMAT 1 — Tab-separated (CTRL+SHIFT+V):
        Company, City \\t Phone \\t Notes?
        Blank lines between entries are normal.

    FORMAT 2 — Smashed (CTRL+V, no tabs):
        Company, City(phone)Company, City(phone)...
        Phone number regex acts as the delimiter.

    Both formats:
    - ALL-CAPS lines with no phone = state header, attached to rows below
    - Blank lines skipped
    - ambiguous=True when no comma to split company/city
    """
    text = tsv_text.strip()
    if not text:
        return []

    if "\t" in text:
        return _parse_tab_format(text)
    return _parse_smashed_format(text)


def _parse_tab_format(text: str) -> list[dict[str, Any]]:
    leads: list[dict[str, Any]] = []
    current_state = ""

    for raw in text.split("\n"):
        line = raw.rstrip("\r")
        cols = line.split("\t")

        if not any(c.strip() for c in cols):
            continue

        first = cols[0].strip()
        rest_empty = all(not c.strip() for c in cols[1:])

        # State header
        if rest_empty and first and _is_state_header(first):
            current_state = first.title()
            continue

        if _is_column_header(first):
            continue

        if not first:
            continue

        phone = cols[1].strip() if len(cols) > 1 else ""
        # Notes column intentionally skipped per spec

        company, city, ambiguous = _split_company_city(first)
        leads.append({
            "company": company,
            "city": city,
            "state": current_state,
            "phone": phone,
            "ambiguous": ambiguous,
        })

    return leads


def _parse_smashed_format(text: str) -> list[dict[str, Any]]:
    """
    Parse smashed (no-tab) format by using phone number as the delimiter.
    Handles multi-line input where state headers appear on their own lines.
    """
    leads: list[dict[str, Any]] = []
    current_state = ""

    lines = text.split("\n")

    for raw in lines:
        line = raw.rstrip("\r").strip()
        if not line:
            continue

        # State header on its own line
        if _is_state_header(line) and not PHONE_RE.search(line):
            current_state = line.title()
            continue

        if _is_column_header(line):
            continue

        # Split this line (or blob) on phone pattern
        # PHONE_RE.split returns: [pre, phone, pre, phone, ..., post]
        parts = PHONE_RE.split(line)
        i = 0
        while i < len(parts):
            company_city = parts[i].strip()
            phone = parts[i + 1].strip() if i + 1 < len(parts) else ""
            i += 2

            if not company_city:
                continue

            company, city, ambiguous = _split_company_city(company_city)
            leads.append({
                "company": company,
                "city": city,
                "state": current_state,
                "phone": phone,
                "ambiguous": ambiguous,
            })

    return leads


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def random_delay(min_s: float = 1.5, max_s: float = 4.0) -> None:
    time.sleep(random.uniform(min_s, max_s))


def _is_good_domain(url: str) -> bool:
    parsed = urlparse(url)
    if not parsed.netloc or not parsed.scheme.startswith("http"):
        return False
    domain = parsed.netloc.lower().lstrip("www.")
    return not any(bad in domain for bad in BAD_DOMAINS)


def _is_valid_email(email: str) -> bool:
    lower = email.lower()
    return not any(j in lower for j in JUNK_EMAIL_SUBSTRINGS)


# ---------------------------------------------------------------------------
# DuckDuckGo company website search
# ---------------------------------------------------------------------------

def search_company_website(
    company: str,
    city: str,
    state: str,
    page: Page,
) -> str | None:
    """
    Search DuckDuckGo HTML interface for the company's official website.
    Returns scheme://netloc or None.
    """
    query = f'"{company}" {city} {state} official site contact'
    search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"

    try:
        page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(random.randint(600, 1000))

        result_links = page.locator("a.result__a").all()
        for link in result_links[:8]:
            href = link.get_attribute("href") or ""
            # DuckDuckGo wraps real URLs in /l/?uddg=<encoded>
            parsed = urlparse(href)
            params = parse_qs(parsed.query)
            actual = params.get("uddg", [""])[0]
            if not actual:
                # Try href directly
                actual = href

            p = urlparse(actual)
            if not p.netloc:
                continue
            candidate = f"{p.scheme or 'https'}://{p.netloc}"
            if _is_good_domain(candidate):
                logger.info("Found website for %s: %s", company, candidate)
                return candidate

    except Exception as exc:
        logger.warning("Website search failed for %s: %s", company, exc)

    return None


# ---------------------------------------------------------------------------
# Contact page crawler
# ---------------------------------------------------------------------------

def crawl_for_contact(website_url: str, page: Page) -> dict[str, Any]:
    """
    Crawl homepage + common contact/about paths to extract email and
    decision-maker name.

    Returns dict with keys: email, contact_name, confidence (0-100).
    """
    result: dict[str, Any] = {
        "email": None,
        "contact_name": None,
        "confidence": 0,
    }
    all_text = ""

    pages_to_try = [website_url] + [
        urljoin(website_url, p) for p in CONTACT_PATHS
    ]

    for url in pages_to_try[:5]:  # cap at 5 pages per lead
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(random.randint(500, 900))
            text = page.locator("body").inner_text(timeout=3000) or ""
            all_text += "\n" + text[:8000]

            # Check this page for email first — stop if found
            email = extract_contact_email(text)
            if email and _is_valid_email(email):
                result["email"] = email
                result["confidence"] += 50
                logger.info("Email found on %s: %s", url, email)
                break

        except Exception as exc:
            logger.debug("Crawl page failed %s: %s", url, exc)

        random_delay(0.8, 2.0)

    # Also scan mailto: links across the page
    if not result["email"]:
        try:
            page.goto(website_url, wait_until="domcontentloaded", timeout=15000)
            mailto_links = page.locator("a[href^='mailto:']").all()
            for ml in mailto_links[:5]:
                href = ml.get_attribute("href") or ""
                email = href.replace("mailto:", "").split("?")[0].strip()
                if email and _is_valid_email(email):
                    result["email"] = email
                    result["confidence"] += 40
                    break
        except Exception:
            pass

    # Decision-maker name extraction
    name = find_decision_maker(all_text)
    if name:
        result["contact_name"] = name
        result["confidence"] += 25

    result["confidence"] = min(result["confidence"], 100)
    return result


# ---------------------------------------------------------------------------
# Decision-maker name extraction
# ---------------------------------------------------------------------------

def find_decision_maker(text: str) -> str | None:
    """
    Look for a proper name immediately adjacent to an owner/manager title.
    Returns "First Last" string or None.
    """
    matches = DECISION_MAKER_RE.findall(text)
    for raw in matches:
        name = raw.strip()
        words = name.split()
        # Sanity: 2-3 words, each capitalized, no all-caps (abbreviations)
        if (
            2 <= len(words) <= 3
            and all(w[0].isupper() and not w.isupper() for w in words)
        ):
            return name
    return None


# ---------------------------------------------------------------------------
# MX record validation
# ---------------------------------------------------------------------------

def validate_email_mx(email: str) -> bool:
    """
    Check that the email's domain has MX records.
    Falls back to A-record lookup if dnspython is unavailable.
    """
    try:
        domain = email.split("@", 1)[1]
    except IndexError:
        return False

    # Try dnspython first (proper MX check)
    try:
        import dns.resolver  # type: ignore
        answers = dns.resolver.resolve(domain, "MX", lifetime=5)
        return len(list(answers)) > 0
    except ImportError:
        pass
    except Exception:
        return False

    # Fallback: plain socket A record lookup
    try:
        import socket
        socket.setdefaulttimeout(5)
        socket.getaddrinfo(domain, None)
        return True
    except Exception:
        return False
