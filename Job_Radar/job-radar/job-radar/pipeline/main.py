"""Job radar pipeline entry point.

Reads config/searches.yaml, hits every configured API/query, scores results
against the master CV, deduplicates against the existing Google Sheet rows,
and appends the new ones.

Run locally: `python -m pipeline.main`
Run in CI:   triggered by .github/workflows/daily-scan.yml
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import yaml

from pipeline.sources import adzuna as adz
from pipeline.sources import arbeitnow as arb
from pipeline.sources import remotive as rem
from pipeline.sources import jsearch as jsc
from pipeline.sources import apify as apf
from pipeline import normalize, score, dedupe, sheets
from pipeline.normalize import Job


def load_config():
    cfg_path = Path(__file__).resolve().parent.parent / "config" / "searches.yaml"
    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cv_path = Path(__file__).resolve().parent.parent / cfg["cv_file"]
    cv_text = cv_path.read_text(encoding="utf-8")
    return cfg, cv_text


def _jsearch_day() -> bool:
    """Run JSearch on odd days only → ~15 runs/month → ~225 calls/month.
    Keeps usage safely inside the 500 calls/month free tier."""
    return datetime.now(timezone.utc).day % 2 == 1


def _apify_day() -> bool:
    """Run Apify scrapers only on Mondays and Thursdays.
    2 runs/week × ~$0.15/run = ~$1.20/month — well inside the $5 free credit."""
    return datetime.now(timezone.utc).weekday() in (0, 3)


def collect(cfg) -> List[Job]:
    """Run every configured search and return a flat list of Job objects."""
    out: List[Job] = []
    max_days_old = cfg.get("max_days_old", 7)

    # --- Adzuna (daily) ---
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

    # --- Arbeitnow (daily) ---
    print("[arbeitnow] starting...")
    raws = arb.fetch(max_pages=cfg.get("arbeitnow_max_pages", 3))
    for r in raws:
        j = normalize.from_arbeitnow(r)
        if j:
            out.append(j)
    print(f"  [arbeitnow] {len(raws)} hits")

    # --- Remotive (daily) ---
    print("[remotive] starting...")
    for query in cfg.get("remotive_queries", []):
        raws = rem.fetch(search=query)
        for r in raws:
            j = normalize.from_remotive(r, query=query)
            if j:
                out.append(j)
        print(f"  [remotive] '{query}': {len(raws)} hits")

    # --- JSearch / LinkedIn+Indeed+Glassdoor (every other day) ---
    rapidapi_key = os.environ.get("RAPIDAPI_KEY")
    if rapidapi_key and _jsearch_day():
        print("[jsearch] starting (LinkedIn + Indeed + Glassdoor)...")
        try:
            js_client = jsc.JSearchClient(api_key=rapidapi_key)
            for query in cfg.get("jsearch_queries", jsc.DEFAULT_QUERIES):
                raws = js_client.search(query=query, num_pages=1, date_posted="week")
                for r in raws:
                    j = normalize.from_jsearch(r, query=query)
                    if j:
                        out.append(j)
                print(f"  [jsearch] '{query}': {len(raws)} hits")
        except Exception as e:
            print(f"[jsearch] failed: {e}")
    elif not rapidapi_key:
        print("[jsearch] skipped — RAPIDAPI_KEY not set")
    else:
        print("[jsearch] skipped — even day (budget scheduling)")

    # --- Apify / LinkedIn + Indeed deep scrape (Mon + Thu only) ---
    apify_token = os.environ.get("APIFY_TOKEN")
    if apify_token and _apify_day():
        print("[apify] starting (LinkedIn + Indeed deep scrape)...")
        try:
            ap_client = apf.ApifyClient(token=apify_token)

            # LinkedIn — all queries in one actor run (cheaper)
            li_queries = cfg.get("apify_linkedin_queries", [
                "HSE specialist", "sustainability analyst",
                "LCA analyst", "carbon accounting", "ESG analyst",
            ])
            li_raws = ap_client.scrape_linkedin(
                queries=li_queries,
                location="Italy",
                max_results=30,
            )
            for r in li_raws:
                j = normalize.from_apify_linkedin(r)
                if j:
                    out.append(j)

            # Indeed — one query per run (different actor)
            for q in cfg.get("apify_indeed_queries", ["sustainability Italy", "HSE Italy"]):
                id_raws = ap_client.scrape_indeed(query=q, location="Italy", max_items=20)
                for r in id_raws:
                    j = normalize.from_apify_indeed(r, query=q)
                    if j:
                        out.append(j)
        except Exception as e:
            print(f"[apify] failed: {e}")
    elif not apify_token:
        print("[apify] skipped — APIFY_TOKEN not set (optional)")
    else:
        print("[apify] skipped — not Mon/Thu (budget scheduling)")

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

    # Enrich with seniority, contract type, description snippet
    for j in jobs:
        normalize.enrich(j)
    print(f"[main] enriched {len(jobs)} jobs")

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
