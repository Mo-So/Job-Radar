"""Remotive public API for remote jobs.

No auth required. Supports keyword search via the `search` parameter.
"""

import time
import requests
from typing import List, Dict, Any

REMOTIVE_URL = "https://remotive.com/api/remote-jobs"


def fetch(search: str = None, limit: int = 100) -> List[Dict[str, Any]]:
    """Fetch remote jobs from Remotive, optionally filtered by `search`."""
    params: Dict[str, Any] = {"limit": limit}
    if search:
        params["search"] = search
    try:
        r = requests.get(REMOTIVE_URL, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
    except requests.exceptions.RequestException as e:
        print(f"[remotive] error: {e}")
        return []
    finally:
        time.sleep(0.3)
    return data.get("jobs", []) or []
