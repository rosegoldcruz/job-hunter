from __future__ import annotations

import re
from pathlib import Path

from docx import Document


SKILL_ALIASES: dict[str, list[str]] = {
    "crm automation": ["crm", "gohighlevel", "ghl", "pipeline", "lead routing"],
    "telephony": ["sip", "voip", "asterisk", "twilio", "telephony", "dialer"],
    "frontend web": ["next.js", "nextjs", "react", "tailwind", "framer motion", "gsap"],
    "python automation": ["python", "automation", "scripting", "workflow"],
    "sales ops": ["sales", "follow-up", "follow up", "kpi", "conversion", "outbound"],
    "compliance": ["compliance", "a2p", "regulated", "fiduciary"],
    "databases": ["sql", "postgres", "supabase", "database"],
    "deployment": ["vercel", "docker", "digitalocean", "deploy", "dns"],
}


def _read_docx(path: Path) -> str:
    doc = Document(path)
    lines = [paragraph.text.strip() for paragraph in doc.paragraphs if paragraph.text.strip()]
    return "\n".join(lines)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_resume_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return _read_docx(path)
    if suffix in {".txt", ".md"}:
        return _read_text(path)
    raise ValueError(f"Unsupported resume file type: {suffix}")


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_skills(resume_text: str) -> list[str]:
    lowered = resume_text.lower()
    found: list[str] = []
    for canonical, aliases in SKILL_ALIASES.items():
        if any(alias in lowered for alias in aliases):
            found.append(canonical)
    return found


def extract_evidence_lines(resume_text: str, max_lines: int = 8) -> list[str]:
    raw_lines = [line.strip(" •-\t") for line in resume_text.splitlines()]
    cleaned = [line for line in raw_lines if len(line) > 30]
    ranked = sorted(cleaned, key=len, reverse=True)
    return ranked[:max_lines]


def default_source_queries(skills: list[str]) -> dict[str, list[str]]:
    queries = {
        "indeed": ["full stack developer", "api development"],
        "linkedin": ["solutions engineer", "technical operations"],
        "craigslist": ["website", "web developer", "automation"],
        "remote": ["full stack developer", "automation engineer"],
        "weworkremotely": ["full stack", "automation", "python"],
    }

    if "crm automation" in skills:
        queries["indeed"].extend(["crm automation", "marketing automation", "revenue operations"])
        queries["linkedin"].extend(["revenue operations", "revops", "integrations engineer"])
        queries["craigslist"].extend(["crm", "funnels", "pipeline"])
        queries["remote"].extend(["crm automation", "marketing automation"])
        queries["weworkremotely"].extend(["crm", "marketing automation"])

    if "telephony" in skills:
        queries["indeed"].extend(["lead routing", "sales automation"])
        queries["linkedin"].extend(["automation engineer", "technical operations"])
        queries["craigslist"].extend(["voip", "twilio", "asterisk", "sms", "a2p"])
        queries["remote"].extend(["api development"])

    if "frontend web" in skills:
        queries["indeed"].extend(["next.js developer", "typescript", "python backend"])
        queries["linkedin"].extend(["full stack developer", "next.js developer", "python engineer"])
        queries["craigslist"].extend(["frontend", "backend", "react", "next.js"])
        queries["remote"].extend(["next.js", "react", "typescript"])
        queries["weworkremotely"].extend(["react", "next.js", "typescript"])

    if "python automation" in skills:
        queries["indeed"].extend(["python backend", "pipeline automation"])
        queries["linkedin"].extend(["automation engineer", "python engineer"])
        queries["craigslist"].extend(["python", "automation"])
        queries["remote"].extend(["python", "automation engineer"])

    if "sales ops" in skills:
        queries["indeed"].extend(["conversion tracking"])
        queries["linkedin"].extend(["revenue operations"])
        queries["craigslist"].extend(["sales", "marketing", "lead generation", "ads"])
        queries["remote"].extend(["solutions engineer"])
        queries["weworkremotely"].extend(["solutions engineer"])

    return queries


def merge_queries(defaults: list[str], configured: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for query in defaults + configured:
        normalized = normalize_whitespace(query.lower())
        if not normalized or normalized in seen:
            continue
        deduped.append(query.strip())
        seen.add(normalized)
    return deduped[:20]


def build_resume_profile(resume_path: Path, configured_queries: dict[str, list[str]]) -> dict[str, object]:
    resume_text = read_resume_text(resume_path)
    skills = extract_skills(resume_text)
    defaults = default_source_queries(skills)
    source_queries = {
        "indeed": merge_queries(defaults["indeed"], configured_queries.get("indeed", [])),
        "linkedin": merge_queries(defaults["linkedin"], configured_queries.get("linkedin", [])),
        "craigslist": merge_queries(defaults["craigslist"], configured_queries.get("craigslist", [])),
        "remote": merge_queries(defaults["remote"], configured_queries.get("remote", [])),
        "weworkremotely": merge_queries(defaults["weworkremotely"], configured_queries.get("weworkremotely", [])),
    }
    return {
        "resume_text": resume_text,
        "skills": skills,
        "evidence_lines": extract_evidence_lines(resume_text),
        "source_queries": source_queries,
    }


def extract_job_keywords(job_text: str, max_items: int = 10) -> list[str]:
    lowered = job_text.lower()
    matches: list[str] = []
    for canonical, aliases in SKILL_ALIASES.items():
        if any(alias in lowered for alias in aliases):
            matches.append(canonical)
    return matches[:max_items]