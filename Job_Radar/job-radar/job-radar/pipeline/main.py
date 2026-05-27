"""Job radar pipeline entry point.

Reads config/searches.yaml, hits every configured API/query, scores results
against the master CV, deduplicates against the existing Google Sheet rows,
and appends the new ones.

Run locally: `python -m pipeline.main`
Run in CI:   triggered by .github/workflows/daily-scan.yml
"""

import sys
from pathlib import Path
from typing import List

import yaml

from pipeline.sources import adzuna as adz
from pipeline.sources import arbeitnow as arb
from pipeline.sources import remotive as rem
from pipeline import normalize, score, dedupe, sheets
from pipeline.normalize import Job


def load_config():
    cfg_path = Path(__file__).resolve().parent.parent / "config" / "searches.yaml"
    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cv_path = Path(__file__).resolve().parent.parent / cfg["cv_file"]
    cv_text = cv_path.read_text(encoding="utf-8")
    return cfg, cv_text


def collect(cfg) -> List[Job]:
    """Run every configured search and return a flat list of Job objects."""
    out: List[Job] = []
    max_days_old = cfg.get("max_days_old", 7)

    # --- Adzuna ---
    if cfg.get("adzuna_searches"):
        print("[adzuna] starting...")
        client = adz.AdzunaClient()
        for block in cfg["adzuna_searches"]:
            country = block["country"]
            where = block.get("where", "")
            for query in block.get("queries", []):
                raws = client.search(
                    what=query,
                    country=country,
                    where=where,
                    max_days_old=max_days_old,
                )
                for r in raws:
                    j = normalize.from_adzuna(r, query=query)
                    if j:
                        out.append(j)
                print(f"  [adzuna] '{query}' in {country}: {len(raws)} hits")

    # --- Arbeitnow ---
    print("[arbeitnow] starting...")
    raws = arb.fetch(max_pages=cfg.get("arbeitnow_max_pages", 3))
    for r in raws:
        j = normalize.from_arbeitnow(r)
        if j:
            out.append(j)
    print(f"  [arbeitnow] {len(raws)} hits")

    # --- Remotive ---
    print("[remotive] starting...")
    for query in cfg.get("remotive_queries", []):
        raws = rem.fetch(search=query)
        for r in raws:
            j = normalize.from_remotive(r, query=query)
            if j:
                out.append(j)
        print(f"  [remotive] '{query}': {len(raws)} hits")

    return out


def main() -> int:
    cfg, cv_text = load_config()
    print(f"[main] CV loaded: {len(cv_text)} chars")

    jobs = collect(cfg)
    print(f"[main] collected {len(jobs)} raw jobs across all sources")

    if not jobs:
        print("[main] no jobs collected; exiting")
        return 0

    score.score_jobs(cv_text, jobs)
    print(f"[main] scored. top={jobs[0].fit_score} / bottom={jobs[-1].fit_score}")

    min_fit = cfg.get("min_fit_score", 30)
    jobs = [j for j in jobs if j.fit_score >= min_fit]
    print(f"[main] after fit_score >= {min_fit}: {len(jobs)} jobs")

    known = sheets.existing_hashes()
    print(f"[main] {len(known)} existing rows in the sheet")

    new = dedupe.filter_new(jobs, known)
    print(f"[main] {len(new)} new jobs to append")

    sheets.append(new)
    print("[main] done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
