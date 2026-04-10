"""
Lead enrichment pipeline.

Search:  Brave Search via requests (no browser — fast, reliable)
Crawl:   Playwright for JS-rendered sites (email extraction from full HTML + JS)
Fallback: email pattern guessing (info@, contact@) validated by MX
"""
from __future__ import annotations

import logging
import random
import re
import time
from typing import Any
from urllib.parse import urljoin, urlparse, quote_plus

import requests as req_lib
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="[enrich] %(message)s")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/138.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
}

CONTACT_PATHS = [
    "/contact",
    "/contact-us",
    "/about",
    "/about-us",
    "/team",
    "/our-team",
    "/staff",
]

# Directory/aggregator domains that are NOT the company's own website
BAD_DOMAINS = [
    "google", "bing", "yahoo", "duckduckgo", "brave.com", "search.brave",
    "facebook", "instagram", "twitter", "x.com", "linkedin",
    "yelp", "yellowpages", "bbb.org", "angi.com", "angieslist",
    "thumbtack", "homeadvisor", "houzz", "porch.com",
    "zillow", "trulia", "realtor.com", "apartments.com", "apartmentlist",
    "costar", "loopnet", "allpropertymanagement",
    "zoominfo", "hoovers", "dnb.com", "manta.com", "crunchbase",
    "superpages", "whitepages", "spokeo", "beenverified",
    "mapquest", "whodoyou", "customerlobby", "enrollbusiness",
    "hub.biz", "bizapedia", "opencorporates",
    "wikipedia", "reddit", "youtube", "nextdoor",
    "simplifyem", "buildium", "appfolio", "propertyware",
]

# Email addresses to discard
JUNK_EMAIL_SUBSTRINGS = [
    "noreply", "no-reply", "do-not-reply", "donotreply",
    "example.com", "test.com", "@domain", "placeholder",
    "your@", "email@email", "john@doe", "sentry.io",
    "wix.com", "squarespace.com", "cloudflare.com", "wordpress.com",
    "support@", "abuse@", "admin@sendgrid",
]

# Owner/decision-maker title keywords — also used to disqualify name words
TITLE_WORDS_SET = {
    "owner", "founder", "president", "ceo", "principal",
    "manager", "broker", "director", "member", "designated", "agent",
}

# Common words that appear capitalized but are NOT person names
NON_NAME_WORDS = {
    "company", "contact", "about", "home", "services", "locations",
    "team", "rent", "lease", "management", "property", "properties",
    "real", "estate", "commercial", "residential", "office", "hours",
    "more", "view", "learn", "read", "click", "here", "submit", "send",
    "apply", "request", "schedule", "call", "email", "phone", "fax",
    "hello", "welcome", "follow", "terms", "privacy", "policy",
    "portfolio", "reviews", "testimonials", "resources", "blog", "news",
    "maintenance", "tenant", "landlord", "vacancy", "pricing", "rates",
}

EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.IGNORECASE)

# Looks for "First Last, Title" — name words separated by SPACES only (not newlines)
# so nav-menu text like "Company\n\nLocations\n\nRent" is never treated as a name
DECISION_MAKER_RE = re.compile(
    r"\b([A-Z][a-z]{1,20}(?: [A-Z][a-z]{1,20}){1,2})\b"   # space-only word sep
    r"[ \t,\|\-–—]{0,8}"                                    # non-newline separator
    r"\b(?:owner|founder|president|c\.?e\.?o\.?|principal|property\s+manager"
    r"|general\s+manager|broker(?:\s+of\s+record)?"
    r"|director|managing\s+member|managing\s+director)\b",
    re.IGNORECASE,
)

# Email prefix guesses (tried in order)
EMAIL_GUESS_PREFIXES = ["info", "contact", "office", "hello", "management", "pm"]

# ---------------------------------------------------------------------------
# TSV / smashed-format parser
# ---------------------------------------------------------------------------

PHONE_RE = re.compile(r"(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})")
STATE_HEADER_RE = re.compile(r"^[A-Z][A-Z\s\-]{2,}$")


def _split_company_city(value: str) -> tuple[str, str, bool]:
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
    Auto-detect format and parse into lead dicts.

    FORMAT 1 — Tab-separated (CTRL+SHIFT+V): Company, City [TAB] Phone
    FORMAT 2 — Smashed (CTRL+V, no tabs): Company, City(phone)Company...
    """
    text = tsv_text.strip()
    if not text:
        return []
    return _parse_tab_format(text) if "\t" in text else _parse_smashed_format(text)


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
        if rest_empty and first and _is_state_header(first):
            current_state = first.title()
            continue
        if _is_column_header(first) or not first:
            continue
        phone = cols[1].strip() if len(cols) > 1 else ""
        company, city, ambiguous = _split_company_city(first)
        leads.append({"company": company, "city": city, "state": current_state,
                      "phone": phone, "ambiguous": ambiguous})
    return leads


def _parse_smashed_format(text: str) -> list[dict[str, Any]]:
    leads: list[dict[str, Any]] = []
    current_state = ""
    for raw in text.split("\n"):
        line = raw.rstrip("\r").strip()
        if not line:
            continue
        if _is_state_header(line) and not PHONE_RE.search(line):
            current_state = line.title()
            continue
        if _is_column_header(line):
            continue
        parts = PHONE_RE.split(line)
        i = 0
        while i < len(parts):
            company_city = parts[i].strip()
            phone = parts[i + 1].strip() if i + 1 < len(parts) else ""
            i += 2
            if not company_city:
                continue
            company, city, ambiguous = _split_company_city(company_city)
            leads.append({"company": company, "city": city, "state": current_state,
                          "phone": phone, "ambiguous": ambiguous})
    return leads


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def random_delay(min_s: float = 1.0, max_s: float = 3.0) -> None:
    time.sleep(random.uniform(min_s, max_s))


def _is_good_domain(url: str) -> bool:
    parsed = urlparse(url)
    if not parsed.netloc or not parsed.scheme.startswith("http"):
        return False
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return not any(bad in domain for bad in BAD_DOMAINS)


def _clean_emails(raw_emails: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for e in raw_emails:
        low = e.lower()
        if any(j in low for j in JUNK_EMAIL_SUBSTRINGS):
            continue
        if low in seen:
            continue
        seen.add(low)
        result.append(e)
    return result


# ---------------------------------------------------------------------------
# Brave Search website finder  (requests only — no browser needed)
# ---------------------------------------------------------------------------

def search_company_website(
    company: str,
    city: str,
    state: str,
    session: req_lib.Session,
) -> str | None:
    """
    Use Brave Search HTML (via plain requests) to find the company's
    official website.  Returns scheme://netloc or None.
    Retries once with a longer backoff on 429 rate-limit responses.
    """
    query = f"{company} {city} {state} official website"
    url = f"https://search.brave.com/search?q={quote_plus(query)}"
    logger.info("Brave search: %s", query)

    for attempt in range(2):
        try:
            r = session.get(url, timeout=15)
            if r.status_code == 429:
                wait = 8 + attempt * 6 + random.uniform(0, 3)
                logger.warning("  Brave rate-limited (429) — waiting %.1fs", wait)
                time.sleep(wait)
                continue
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")

            for a in soup.select("a[href]"):
                href = a.get("href", "")
                if not href.startswith("http"):
                    continue
                p = urlparse(href)
                candidate = f"{p.scheme}://{p.netloc}"
                if _is_good_domain(candidate):
                    logger.info("  → website found: %s", candidate)
                    return candidate

            break  # No 429 — no results but don't retry

        except req_lib.exceptions.HTTPError:
            pass  # handled by status_code check above
        except Exception as exc:
            logger.warning("Brave search failed for %s: %s", company, exc)
            break

    logger.info("  → no website found for %s", company)
    return None


# ---------------------------------------------------------------------------
# Contact page crawler  (Playwright for JS-rendered sites)
# ---------------------------------------------------------------------------

def crawl_for_contact(website_url: str, page: Any) -> dict[str, Any]:
    """
    Crawl homepage + contact/about paths with Playwright.
    Extracts email from: JS-evaluated mailto links, full HTML source,
    rendered body text.  Falls back to email pattern guessing.

    Returns: {email, contact_name, confidence, guessed}
    """
    result: dict[str, Any] = {
        "email": None,
        "contact_name": None,
        "confidence": 0,
        "guessed": False,
    }
    all_text = ""
    pages_to_try = [website_url] + [urljoin(website_url, p) for p in CONTACT_PATHS]

    for url in pages_to_try[:5]:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(700)

            # ── 1. JS-evaluated mailto: links (most reliable) ──────────────
            mailto_hrefs: list[str] = page.evaluate(
                "Array.from(document.querySelectorAll('a[href]'))"
                ".map(a=>a.href)"
                ".filter(h=>h.startsWith('mailto:'))"
            )
            for href in mailto_hrefs:
                em = href.replace("mailto:", "").split("?")[0].strip()
                cleaned = _clean_emails([em])
                if cleaned:
                    logger.info("  Email via mailto on %s: %s", url, cleaned[0])
                    result["email"] = cleaned[0]
                    result["confidence"] = 75
                    break

            if result["email"]:
                break

            # ── 2. Full page HTML scan (catches obfuscated/attr emails) ────
            html = page.content()
            emails = _clean_emails(EMAIL_RE.findall(html))
            if emails:
                logger.info("  Email via HTML scan on %s: %s", url, emails[0])
                result["email"] = emails[0]
                result["confidence"] = 60
                break

            # ── 3. Rendered body text ───────────────────────────────────────
            text = page.locator("body").inner_text(timeout=3000) or ""
            all_text += "\n" + text
            emails = _clean_emails(EMAIL_RE.findall(text))
            if emails:
                logger.info("  Email via body text on %s: %s", url, emails[0])
                result["email"] = emails[0]
                result["confidence"] = 55
                break

        except Exception as exc:
            logger.debug("  Crawl page failed %s: %s", url, exc)

        random_delay(0.5, 1.5)

    # ── 4. Email guess fallback (info@, contact@, ...) ──────────────────────
    if not result["email"]:
        domain = urlparse(website_url).netloc.lstrip("www.")
        guessed = _guess_email(domain)
        if guessed:
            logger.info("  Email guessed for %s: %s", domain, guessed)
            result["email"] = guessed
            result["confidence"] = 20
            result["guessed"] = True

    # ── 5. Decision-maker name ─────────────────────────────────────────────
    name = find_decision_maker(all_text)
    if name:
        logger.info("  Contact name found: %s", name)
        result["contact_name"] = name
        result["confidence"] = min(result["confidence"] + 15, 100)

    return result


# ---------------------------------------------------------------------------
# Decision-maker name extraction
# ---------------------------------------------------------------------------

def find_decision_maker(text: str) -> str | None:
    """
    Look for 'First Last — Title' patterns. Validates each candidate to
    ensure no word is a title/junk word and each word is properly cased.
    """
    for raw in DECISION_MAKER_RE.findall(text):
        name = raw.strip()
        words = name.split()
        if not (2 <= len(words) <= 3):
            continue
        # Each word: first char upper, rest all lower (no mixed-case abbrev)
        if not all(len(w) >= 2 and w[0].isupper() and w[1:].islower() for w in words):
            continue
        # No word is a known title or non-name word
        if any(w.lower() in TITLE_WORDS_SET or w.lower() in NON_NAME_WORDS for w in words):
            continue
        return name
    return None


# ---------------------------------------------------------------------------
# Email guess fallback
# ---------------------------------------------------------------------------

def _guess_email(domain: str) -> str | None:
    """
    Try info@domain, contact@domain etc.
    Only proceeds if domain has MX records (proves it accepts email).
    Returns the first valid-format guess, or None.
    """
    if not validate_email_mx(f"probe@{domain}"):
        return None
    for prefix in EMAIL_GUESS_PREFIXES:
        return f"{prefix}@{domain}"
    return None


# ---------------------------------------------------------------------------
# MX record validation
# ---------------------------------------------------------------------------

def validate_email_mx(email: str) -> bool:
    """Check that the email domain has MX (or A) records."""
    try:
        domain = email.split("@", 1)[1]
    except IndexError:
        return False

    try:
        import dns.resolver  # type: ignore
        dns.resolver.resolve(domain, "MX", lifetime=5)
        return True
    except ImportError:
        pass
    except Exception:
        return False

    try:
        import socket
        socket.setdefaulttimeout(5)
        socket.getaddrinfo(domain, None)
        return True
    except Exception:
        return False
