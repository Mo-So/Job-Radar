"""Normalize raw provider responses into a common Job schema.

Every source has its own field names; this module is the seam where they all
become a single shape the rest of the pipeline can consume.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import hashlib
import re


@dataclass
class Job:
    source: str          # "adzuna" / "arbeitnow" / "remotive"
    source_id: str       # provider's own id
    title: str
    company: str
    location: str        # plain string
    remote: bool
    posted_date: str     # ISO date string (YYYY-MM-DD)
    description: str     # plain text (HTML stripped)
    apply_url: str
    salary: str = ""
    raw_query: str = ""  # the search query that surfaced this job
    fit_score: float = 0.0

    def hash_key(self) -> str:
        """Stable dedup hash: company + title + location, normalized."""
        key = "|".join([
            self.company.strip().lower(),
            self.title.strip().lower(),
            self.location.strip().lower(),
        ])
        return hashlib.md5(key.encode("utf-8")).hexdigest()[:16]


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


def from_remotive(raw: dict, query: str = "") -> Optional[Job]:
    try:
        return Job(
            source="remotive",
            source_id=str(raw.get("id") or ""),
            title=(raw.get("title") or "").strip(),
            company=(raw.get("company_name") or "").strip(),
            location=(raw.get("candidate_required_location") or "Worldwide").strip(),
            remote=True,  # Remotive is remote-only
            posted_date=(raw.get("publication_date") or "")[:10],
            description=_strip_html(raw.get("description") or ""),
            apply_url=raw.get("url") or "",
            salary=raw.get("salary") or "",
            raw_query=query,
        )
    except Exception as e:
        print(f"[normalize] remotive error: {e}")
        return None
