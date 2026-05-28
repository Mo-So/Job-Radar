"""JSearch API client (via RapidAPI).

Single free API that aggregates LinkedIn, Indeed, Glassdoor, ZipRecruiter,
and Google Jobs simultaneously. Free tier: 500 requests/month.

Sign up: https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch
After subscribing (free plan), copy your RapidAPI key to the
RAPIDAPI_KEY environment variable / GitHub secret.

500 calls/month budget with this config:
  ~15 queries/day × 1 page each = 15 calls/day → would exceed budget.
  So we run JSearch every OTHER day via the date check in main.py,
  spending ~225 calls/month. Safe.
"""

import os
import time
import requests
from typing import List, Dict, Any

JSEARCH_URL = "https://jsearch.p.rapidapi.com/search"

# Maps our human query → what JSearch sends.
# JSearch's `query` field understands natural-language job titles, tools,
# and location qualifiers — "LCA analyst Italy remote" works well.
DEFAULT_QUERIES = [
    "HSE specialist Italy",
    "EHS specialist Italy",
    "sustainability analyst Italy",
    "LCA analyst Europe remote",
    "carbon accounting specialist Europe",
    "ESG analyst Italy",
    "SimaPro LCA specialist",
    "life cycle assessment specialist Europe",
    "environmental engineer Italy",
    "sustainability specialist remote Europe",
    "GHG protocol analyst Europe",
    "CSRD sustainability analyst Europe",
]


class JSearchClient:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("RAPIDAPI_KEY")
        if not self.api_key:
            raise RuntimeError(
                "RAPIDAPI_KEY environment variable is required. "
                "Get a free key at https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch"
            )
        self.headers = {
            "X-RapidAPI-Key": self.api_key,
            "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
        }

    def search(
        self,
        query: str,
        num_pages: int = 1,
        date_posted: str = "week",  # "today" | "3days" | "week" | "month"
        remote_jobs_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """Search JSearch for jobs matching `query`.

        Args:
            query: natural-language query e.g. "sustainability analyst Italy"
            num_pages: pages to fetch (each page = 10 results, costs 1 call)
            date_posted: freshness filter
            remote_jobs_only: if True, only return remote positions

        Returns:
            List of raw job dicts from JSearch.
        """
        params = {
            "query": query,
            "num_pages": num_pages,
            "date_posted": date_posted,
        }
        if remote_jobs_only:
            params["remote_jobs_only"] = "true"

        try:
            r = requests.get(
                JSEARCH_URL,
                headers=self.headers,
                params=params,
                timeout=30,
            )
            if r.status_code == 429:
                print(f"[jsearch] rate limited on '{query}', skipping")
                return []
            r.raise_for_status()
            data = r.json()
            return data.get("data") or []
        except requests.exceptions.RequestException as e:
            print(f"[jsearch] error for '{query}': {e}")
            return []
        finally:
            time.sleep(0.8)  # polite — RapidAPI is rate-limited per second too
