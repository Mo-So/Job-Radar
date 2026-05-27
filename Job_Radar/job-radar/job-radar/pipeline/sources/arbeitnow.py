"""Arbeitnow public job board API.

No auth required. Endpoint returns paginated JSON of European/remote jobs,
heavily tech-skewed but includes some sustainability and ops roles.
"""

import time
import requests
from typing import List, Dict, Any

ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"


def fetch(max_pages: int = 3) -> List[Dict[str, Any]]:
    """Fetch up to `max_pages` of Arbeitnow listings.

    Each page returns ~100 jobs. We rely on the pipeline's fit-score filter
    to drop the irrelevant ones rather than pre-filtering here.
    """
    all_jobs: List[Dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        try:
            r = requests.get(ARBEITNOW_URL, params={"page": page}, timeout=30)
            r.raise_for_status()
            data = r.json()
        except requests.exceptions.RequestException as e:
            print(f"[arbeitnow] error on page {page}: {e}")
            break
        jobs = data.get("data") or []
        if not jobs:
            break
        all_jobs.extend(jobs)
        time.sleep(0.3)
    return all_jobs
