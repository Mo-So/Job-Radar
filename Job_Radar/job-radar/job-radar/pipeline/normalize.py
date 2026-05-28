"""Normalize raw provider responses into a common Job schema.

Every source has its own field names; this module is the seam where they all
become a single shape the rest of the pipeline can consume.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import hashlib
import re


# ── Seniority & contract detection ───────────────────────────────────────────

_SENIOR_TITLE = re.compile(
    r'\b(senior|sr\.?|lead|principal|head of|manager|director|expert)\b', re.I)
_JUNIOR_TITLE = re.compile(
    r'\b(junior|jr\.?|entry.?level|graduate|intern|stage|tirocinio|apprendista)\b', re.I)
_YEARS_PATTERN = re.compile(
    r'(\d+)\s*[\+\-\u2013]?\s*(?:to|-|\u2013)\s*(\d+)\s+(?:years?|anni)|'
    r'(\d+)\s*\+?\s+(?:years?|anni)\s+(?:of\s+)?(?:experience|esperienza)|'
    r'(?:minimum|almeno|at least|minimo)\s+(\d+)\s+(?:years?|anni)|'
    r'(\d+)\s*\+\s*(?:years?|anni)',
    re.I,
)
_CONTRACT_PATTERNS = {
    'Full-time':  re.compile(r'\b(full.?time|tempo pieno|a tempo pieno)\b', re.I),
    'Part-time':  re.compile(r'\b(part.?time|tempo parziale)\b', re.I),
    'Contract':   re.compile(r'\b(contract|freelance|contratto a termine|determinato)\b', re.I),
    'Internship': re.compile(r'\b(intern(ship)?|stage|tirocinio|apprendistato)\b', re.I),
}


def detect_seniority(title: str, description: str):
    """Return (seniority_label, years_exp_string)."""
    blob = f"{title} {description[:3000]}"
    years_found = []
    for m in _YEARS_PATTERN.finditer(blob):
        for g in m.groups():
            if g and g.isdigit():
                years_found.append(int(g))

    years_str = ""
    seniority = "Unknown"

    if years_found:
        min_y = min(years_found)
        max_y = max(years_found)
        years_str = f"{min_y}" if min_y == max_y else f"{min_y}-{max_y}"
        if max_y <= 2:
            seniority = "Junior"
        elif max_y <= 4:
            seniority = "Mid"
        else:
            seniority = "Senior"

    if _SENIOR_TITLE.search(title):
        seniority = "Senior"
    elif _JUNIOR_TITLE.search(title):
        seniority = "Junior"

    return seniority, years_str


def detect_contract(title: str, description: str) -> str:
    blob = f"{title} {description[:2000]}"
    for label, pattern in _CONTRACT_PATTERNS.items():
        if pattern.search(blob):
            return label
    return ""


# ── Job dataclass ─────────────────────────────────────────────────────────────

@dataclass
class Job:
    source: str
    source_id: str
    title: str
    company: str
    location: str
    remote: bool
    posted_date: str
    description: str
    apply_url: str
    salary: str = ""
    raw_query: str = ""
    fit_score: float = 0.0
    seniority: str = ""
    years_exp: str = ""
    contract_type: str = ""
    description_snippet: str = ""

    def hash_key(self) -> str:
        """Stable dedup hash: company + title + location, normalized."""
        key = "|".join([
            self.company.strip().lower(),
            self.title.strip().lower(),
            self.location.strip().lower(),
        ])
        return hashlib.md5(key.encode("utf-8")).hexdigest()[:16]


def enrich(job: Job) -> Job:
    """Populate derived fields (seniority, contract_type, snippet) in-place."""
    job.seniority, job.years_exp = detect_seniority(job.title, job.description)
    job.contract_type = detect_contract(job.title, job.description)
    job.description_snippet = job.description[:500].strip()
    return job


# ── Helpers ───────────────────────────────────────────────────────────────────

def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


_REMOTE_HINTS = (
    "remote", "work from home", "smart working", "telelavoro",
    "lavoro da casa", "fully remote", "home office",
)


def _detect_remote(*texts: str) -> bool:
    blob = " ".join(t for t in texts if t).lower()
    return any(h in blob for h in _REMOTE_HINTS)


def _adzuna_salary(raw: dict) -> str:
    smin, smax = raw.get("salary_min"), raw.get("salary_max")
    if not smin and not smax:
        return ""
    suffix = " (est)" if raw.get("salary_is_predicted") in ("1", 1, True) else ""
    if smin and smax and smin != smax:
        return f"{int(smin):,}-{int(smax):,}{suffix}"
    val = smin or smax
    return f"{int(val):,}{suffix}"


# ── Per-source normalizers ────────────────────────────────────────────────────

def from_adzuna(raw: dict, query: str = "") -> Optional[Job]:
    try:
        title = (raw.get("title") or "").strip()
        company = ((raw.get("company") or {}).get("display_name") or "").strip()
        location = ((raw.get("location") or {}).get("display_name") or "").strip()
        description = _strip_html(raw.get("description") or "")
        return Job(
            source="adzuna",
            source_id=str(raw.get("id") or ""),
            title=title,
            company=company,
            location=location,
            remote=_detect_remote(title, description, location),
            posted_date=(raw.get("created") or "")[:10],
            description=description,
            apply_url=raw.get("redirect_url") or "",
            salary=_adzuna_salary(raw),
            raw_query=query,
        )
    except Exception as e:
        print(f"[normalize] adzuna error: {e}")
        return None


def from_arbeitnow(raw: dict) -> Optional[Job]:
    try:
        ts = raw.get("created_at")
        posted = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d") if isinstance(ts, (int, float)) and ts else ""
        return Job(
            source="arbeitnow",
            source_id=str(raw.get("slug") or ""),
            title=(raw.get("title") or "").strip(),
            company=(raw.get("company_name") or "").strip(),
            location=(raw.get("location") or "").strip(),
            remote=bool(raw.get("remote", False)),
            posted_date=posted,
            description=_strip_html(raw.get("description") or ""),
            apply_url=raw.get("url") or "",
            salary="",
            raw_query="",
        )
    except Exception as e:
        print(f"[normalize] arbeitnow error: {e}")
        return None


def from_jsearch(raw: dict, query: str = "") -> Optional[Job]:
    try:
        title = (raw.get("job_title") or "").strip()
        company = (raw.get("employer_name") or "").strip()
        city = raw.get("job_city") or ""
        country = raw.get("job_country") or ""
        location = ", ".join(filter(None, [city, country])).strip()
        description = _strip_html(raw.get("job_description") or "")
        apply_url = raw.get("job_apply_link") or raw.get("job_google_link") or ""
        posted_at = raw.get("job_posted_at_datetime_utc") or ""
        posted_date = posted_at[:10] if posted_at else ""
        source_platform = raw.get("job_publisher") or "jsearch"
        salary_min = raw.get("job_min_salary")
        salary_max = raw.get("job_max_salary")
        salary = ""
        if salary_min or salary_max:
            period = raw.get("job_salary_period") or ""
            currency = raw.get("job_salary_currency") or ""
            lo = f"{int(salary_min):,}" if salary_min else "?"
            hi = f"{int(salary_max):,}" if salary_max else "?"
            salary = f"{currency} {lo}-{hi} {period}".strip()
        return Job(
            source=f"jsearch:{source_platform.lower()}",
            source_id=str(raw.get("job_id") or ""),
            title=title,
            company=company,
            location=location,
            remote=bool(raw.get("job_is_remote", False)),
            posted_date=posted_date,
            description=description,
            apply_url=apply_url,
            salary=salary,
            raw_query=query,
        )
    except Exception as e:
        print(f"[normalize] jsearch error: {e}")
        return None


def from_apify_linkedin(raw: dict) -> Optional[Job]:
    try:
        location = (raw.get("location") or raw.get("place") or "").strip()
        description = _strip_html(raw.get("description") or raw.get("descriptionHtml") or "")
        return Job(
            source="apify:linkedin",
            source_id=str(raw.get("id") or raw.get("jobId") or ""),
            title=(raw.get("title") or raw.get("jobTitle") or "").strip(),
            company=(raw.get("companyName") or raw.get("company") or "").strip(),
            location=location,
            remote=_detect_remote(location, description),
            posted_date=(raw.get("postedAt") or "")[:10],
            description=description,
            apply_url=raw.get("applyUrl") or raw.get("url") or "",
            salary=raw.get("salary") or "",
            raw_query="",
        )
    except Exception as e:
        print(f"[normalize] apify:linkedin error: {e}")
        return None


def from_remotive(raw: dict, query: str = "") -> Optional[Job]:
    try:
        return Job(
            source="remotive",
            source_id=str(raw.get("id") or ""),
            title=(raw.get("title") or "").strip(),
            company=(raw.get("company_name") or "").strip(),
            location=(raw.get("candidate_required_location") or "Worldwide").strip(),
            remote=True,
            posted_date=(raw.get("publication_date") or "")[:10],
            description=_strip_html(raw.get("description") or ""),
            apply_url=raw.get("url") or "",
            salary=raw.get("salary") or "",
            raw_query=query,
        )
    except Exception as e:
        print(f"[normalize] remotive error: {e}")
        return None
