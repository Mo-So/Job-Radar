"""Skip jobs already in the archive, and collapse duplicates within a batch."""

from typing import List, Set
from pipeline.normalize import Job


def filter_new(jobs: List[Job], known_hashes: Set[str]) -> List[Job]:
    """Return jobs whose hash is not in `known_hashes`.

    Also collapses duplicates within the input list (same hash from multiple
    sources or queries), keeping the one with the highest fit score.
    """
    best_by_hash = {}
    for j in jobs:
        h = j.hash_key()
        if h in known_hashes:
            continue
        existing = best_by_hash.get(h)
        if existing is None or j.fit_score > existing.fit_score:
            best_by_hash[h] = j
    return list(best_by_hash.values())
