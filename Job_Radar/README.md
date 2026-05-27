# Job radar

Automated daily scan of free job-board APIs (Adzuna, Arbeitnow, Remotive),
scored against your CV with a local sentence-transformer model, archived to
Google Sheets. Runs free on GitHub Actions — no hosting cost, no Claude
API tokens consumed, no provider that requires payment.

## How it works

1. GitHub Actions wakes up daily at 06:00 UTC and runs `pipeline/main.py`.
2. The script queries Adzuna (multiple countries × keywords), Arbeitnow, and
   Remotive for fresh jobs.
3. Each job is encoded with `sentence-transformers/all-MiniLM-L6-v2` and
   compared to your CV via cosine similarity → a 0-100 fit score.
4. Jobs below `min_fit_score` are discarded; the rest are deduplicated against
   the existing sheet (hash of company + title + location).
5. New rows are appended to your Google Sheet.

## One-time setup

### 1. Adzuna API key (free)

1. Go to <https://developer.adzuna.com/> and register.
2. Create an application; you'll get an `App ID` and `App Key`.
3. Note: free tier limits are not publicly published but the community
   consensus is roughly 1,000 calls/month. The default `searches.yaml` uses
   about 600/month.

### 2. Google Service Account + Sheet

The pipeline writes to Google Sheets using a service account (no OAuth dance,
no expiring tokens).

1. Open <https://console.cloud.google.com/> and create a new project (call it
   anything, e.g. `job-radar`).
2. Enable the **Google Sheets API** and the **Google Drive API** for that
   project (APIs & Services → Library).
3. Go to **IAM & Admin → Service Accounts → Create service account**.
   Give it any name (e.g. `job-radar-bot`); no role needed.
4. Open the new service account → **Keys → Add key → JSON**. A JSON file
   downloads — keep it safe, you'll paste its content as a GitHub secret.
5. Open the JSON file in a text editor and copy the `client_email` value
   (looks like `job-radar-bot@your-project.iam.gserviceaccount.com`).
6. Create a new Google Sheet (call it e.g. `Job radar`). From the address bar,
   copy the `SHEET_ID` — the long string between `/d/` and `/edit`.
7. Share the sheet with the service account's `client_email`, giving it
   **Editor** access. (This step is essential — without it the script gets a
   403.)

### 3. GitHub repo

1. Create a new GitHub repo (private is fine).
2. Push the contents of this folder to it.
3. In the repo, go to **Settings → Secrets and variables → Actions → New
   repository secret** and add four secrets:

   | Name | Value |
   |---|---|
   | `ADZUNA_APP_ID` | your Adzuna App ID |
   | `ADZUNA_APP_KEY` | your Adzuna App Key |
   | `GOOGLE_SERVICE_ACCOUNT_JSON` | paste the **entire** JSON file content |
   | `SHEET_ID` | the long ID from your sheet's URL |

4. Open the **Actions** tab and enable workflows if prompted.

### 4. First run

Open **Actions → Daily job scan → Run workflow** to trigger a manual run.
The first run installs deps and downloads the sentence-transformer model
(~3-5 minutes). Subsequent runs use the cache and finish in ~30 seconds.

If everything is wired up, you'll see new rows appear in your sheet
within a few seconds of the run completing.

## Tuning

Everything user-tunable lives in `config/searches.yaml`:

- **Keywords**: add/remove queries per country. Each query becomes one
  Adzuna API call — watch the monthly call budget if you go big.
- **Countries**: add `fr`, `gb`, `es`, etc. by copying an existing block.
- **`max_days_old`**: how far back to look on Adzuna. 7 is the default.
- **`min_fit_score`**: filter floor. Start at 35, tune to taste.

To improve the fit-score quality, replace `config/cv.txt` with a more
complete **master CV** — one long document containing every project,
achievement, tool, and certification you have, not the trimmed version you
send to applications. The fit-score is a semantic match between this text
and the job description, so the richer the CV text, the more discerning
the score.

## Local testing

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export ADZUNA_APP_ID=...
export ADZUNA_APP_KEY=...
export GOOGLE_SERVICE_ACCOUNT_JSON="$(cat /path/to/service_account.json)"
export SHEET_ID=...

python -m pipeline.main
```

## Cost summary

| Service | Cost | Note |
|---|---|---|
| GitHub Actions | Free | 2,000 minutes/month free tier; ~15 used |
| Adzuna API | Free | ~600 calls/month with default config |
| Arbeitnow API | Free | Public, no auth |
| Remotive API | Free | Public, no auth |
| Google Sheets API | Free | Generous free tier |
| Sentence-transformers | Free | Runs locally on the Actions runner |

Total monthly cost: zero.

## Weekly review with Claude

The pipeline deliberately does **not** call the Claude API (that would burn
real tokens). Instead, once a week:

1. Open your Google Sheet, sort by `fit_score` descending.
2. Pick the top 10-15 unreviewed rows.
3. Paste them into a Claude chat with the prompt:
   > "For each of these jobs, identify (a) the strongest match with my CV,
   > (b) the biggest gap, and (c) draft a 3-sentence cover letter opening
   > tailored to that role."

That's where your Pro subscription earns its keep — depth on the handful
of jobs that matter, not breadth on every posting.

## Known limitations

- **LinkedIn is not in the automated loop.** LinkedIn's ToS prohibits
  scraping. Keep native LinkedIn job alerts running in your account in
  parallel; we can add an email-parsing step later if you want.
- **Free job APIs have coverage gaps**, especially for senior or niche
  roles. The pipeline is best at catching *new* postings across many
  small/medium companies — not at finding everything that exists.
- **Fit score is a triage signal, not a verdict.** Expect ~70-80%
  agreement with how you'd actually rank matches. Use it for sorting,
  not for deciding to skip something interesting.
