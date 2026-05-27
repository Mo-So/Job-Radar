"""Write jobs to Google Sheets via a service account.

You need to share the sheet with the service account's email
(client_email field in the JSON key) — otherwise gspread will return a
permission error.
"""

import os
import json
from datetime import datetime, timezone
from typing import List, Set

import gspread
from google.oauth2.service_account import Credentials

from pipeline.normalize import Job


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

HEADERS = [
    "hash", "added_at", "source", "title", "company", "location",
    "remote", "posted_date", "fit_score", "salary", "apply_url",
    "raw_query", "status", "notes",
]


def _open_sheet():
    creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    sheet_id = os.environ.get("SHEET_ID")
    if not creds_json or not sheet_id:
        raise RuntimeError(
            "GOOGLE_SERVICE_ACCOUNT_JSON and SHEET_ID environment variables are required."
        )
    info = json.loads(creds_json)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(sheet_id)
    return sh.sheet1


def existing_hashes() -> Set[str]:
    """Read the sheet's first column. Writes the header row if the sheet is empty."""
    ws = _open_sheet()
    rows = ws.get_all_values()
    if not rows:
        ws.update("A1", [HEADERS])
        return set()
    if rows[0] != HEADERS:
        # Header mismatch — assume fresh sheet, overwrite header
        ws.clear()
        ws.update("A1", [HEADERS])
        return set()
    return {r[0] for r in rows[1:] if r and r[0]}


def append(jobs: List[Job]) -> None:
    if not jobs:
        return
    ws = _open_sheet()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    rows = []
    for j in jobs:
        rows.append([
            j.hash_key(),
            now,
            j.source,
            j.title,
            j.company,
            j.location,
            "TRUE" if j.remote else "FALSE",
            j.posted_date,
            j.fit_score,
            j.salary,
            j.apply_url,
            j.raw_query,
            "",  # status — manually updated in the sheet
            "",  # notes
        ])
    ws.append_rows(rows, value_input_option="USER_ENTERED")
