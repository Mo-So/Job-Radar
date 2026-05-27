"""Adzuna API client.

Free tier requires app_id + app_key from https://developer.adzuna.com/.
Adzuna's `what` parameter searches BOTH title and description, so a query
like 'SimaPro' surfaces every job that mentions SimaPro anywhere — even
if the official title is something like 'Project Engineer'.
"""

import os
import time
import requests
from typing import List, Dict, Any

ADZUNA_BASE = "https://api.adzuna.com/v1/api"


class AdzunaClient:
    def __init__(self, app_id: str = None, app_key: str = None):
        self.app_id = app_id or os.environ.get("ADZUNA_APP_ID")
        self.app_key = app_key or os.environ.get("ADZUNA_APP_KEY")
        if not self.app_id or not self.app_key:
            raise RuntimeError(
                "ADZUNA_APP_ID and ADZUNA_APP_KEY environment variables are required. "
                "Register at https://developer.adzuna.com/ to get them."
            )

    def search(
        self,
        what: str,
        country: str = "it",
        where: str = "",
        results_per_page: int = 50,
        max_days_old: int = 7,
    ) -> List[Dict[str, Any]]:
        """Search Adzuna for jobs matching `what` in `country`.

        Args:
            what: free-text query (matches title and description)
            country: two-letter country code (it, gb, de, fr, nl, es, ...)
            where: location string within country (empty = whole country)
            results_per_page: 10-50 (max 50)
            max_days_old: filter to jobs posted within last N days

        Returns:
            List of raw job dicts. Empty list on error.
        """
        url = f"{ADZUNA_BASE}/jobs/{country}/search/1"
        params = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "what": what,
            "where": where,
            "results_per_page": min(50, max(10, results_per_page)),
            "max_days_old": max_days_old,
            "content-type": "application/json",
        }
        try:
            r = requests.get(url, params=params, timeout=30)
            if r.status_code == 429:
                print(f"[adzuna] rate limited on '{what}' in {country}, waiting 5s")
                time.sleep(5)
                return []
            r.raise_for_status()
            data = r.json()
            return data.get("results", []) or []
        except requests.exceptions.RequestException as e:
            print(f"[adzuna] error for '{what}' in {country}: {e}")
            return []
        finally:
            time.sleep(0.4)  # polite throttle
