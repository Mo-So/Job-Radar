"""Apify client for supplementary job scraping.

Apify free tier: $5/month credit (auto-renewed, no card needed to start).
Two actors used:
  1. LinkedIn Jobs scraper  — catches company-direct LinkedIn postings
  2. Indeed scraper         — backup for any Indeed listings JSearch misses

Sign up: https://apify.com/ → get your API token from
Settings → Integrations → API token.
Add it as APIFY_TOKEN GitHub secret.

Each actor RUN costs roughly $0.10–0.25 from your $5 credit, depending
on how many results you pull. Config below is set conservatively so you
stay within the free tier across the whole month.
"""

import os
import time
import requests
from typing import List, Dict, Any

APIFY_BASE = "https://api.apify.com/v2"

# Actor IDs — these are stable Apify actor identifiers
LINKEDIN_ACTOR = "curious_coder~linkedin-jobs-scraper"
INDEED_ACTOR = "misceres~indeed-scraper"


class ApifyClient:
    def __init__(self, token: str = None):
        self.token = token or os.environ.get("APIFY_TOKEN")
        if not self.token:
            raise RuntimeError(
                "APIFY_TOKEN environment variable is required. "
                "Get a free token at https://apify.com/ → Settings → Integrations."
            )

    def _run_actor(
        self,
        actor_id: str,
        input_data: Dict[str, Any],
        timeout_secs: int = 120,
    ) -> List[Dict[str, Any]]:
        """Synchronously run an Apify actor and return its dataset items.

        Uses the /run-sync-get-dataset-items endpoint so we get results
        in one HTTP call without polling.
        """
        url = f"{APIFY_BASE}/acts/{actor_id}/run-sync-get-dataset-items"
        params = {
            "token": self.token,
            "timeout": timeout_secs,
            "memory": 256,  # MB — minimum, keeps cost low
        }
        try:
            r = requests.post(
                url,
                params=params,
                json=input_data,
                timeout=timeout_secs + 30,
            )
            if r.status_code == 402:
                print(f"[apify] payment required — free credit exhausted for this month")
                return []
            if r.status_code == 429:
                print(f"[apify] rate limited")
                return []
            r.raise_for_status()
            return r.json() or []
        except requests.exceptions.RequestException as e:
            print(f"[apify] actor {actor_id} error: {e}")
            return []

    def scrape_linkedin(
        self,
        queries: List[str],
        location: str = "Italy",
        max_results: int = 25,
    ) -> List[Dict[str, Any]]:
        """Scrape LinkedIn Jobs for each query.

        Keeps max_results low to conserve free credits.
        Runs one actor call per location (passes all queries at once).
        """
        input_data = {
            "searchQueries": queries,
            "location": location,
            "maxResults": max_results,
            "datePosted": "Past Week",
        }
        results = self._run_actor(LINKEDIN_ACTOR, input_data)
        print(f"[apify:linkedin] {len(results)} results for {location}")
        time.sleep(1)
        return results

    def scrape_indeed(
        self,
        query: str,
        location: str = "Italy",
        max_items: int = 30,
    ) -> List[Dict[str, Any]]:
        """Scrape Indeed for a single query + location."""
        input_data = {
            "query": query,
            "location": location,
            "maxItems": max_items,
            "startUrls": [],
        }
        results = self._run_actor(INDEED_ACTOR, input_data)
        print(f"[apify:indeed] '{query}' in {location}: {len(results)} results")
        time.sleep(1)
        return results
