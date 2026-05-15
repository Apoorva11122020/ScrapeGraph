# ScrapeAI — Company sheet → website URL → ScrapeGraphAI Extract

Python workflow that reads company names from the client Excel workbook, discovers an official website URL, calls **ScrapeGraphAI v2 `/api/extract`** with the agreed prompt + JSON schema, and writes **Excel/CSV** with one row per company (failures keep the row with `status` + `error_detail`).

## Scaling (~20k companies)

| Method | Best for | Notes |
|--------|----------|--------|
| **Google Programmable Search** (`GOOGLE_CSE_API_KEY` + `GOOGLE_CSE_CX`) | Production | Predictable quota, no browser CAPTCHA, ToS-aligned vs scraping google.com. **Use `SEARCH_PROVIDER=auto` (default) when keys are set.** |
| **DuckDuckGo HTML + BeautifulSoup** | Fallback / trial | No API key; may rate-limit or change HTML — OK for smaller batches. |
| **Playwright on google.com** | Dev / last resort | High CAPTCHA risk; enable only with `SEARCH_PROVIDER=playwright` or `SEARCH_PLAYWRIGHT_FALLBACK=true`. |

Dependencies: **httpx** + **beautifulsoup4** for DDG; **playwright** optional unless you use the Playwright path.

## Repo layout

- `apoorva trail sheet.xlsx` — trial input (column `COMPANY NAME`, header on row 2 → pandas `header=1`).
- `src/scrape_ai_workflow/` — package (`pipeline`, `google_discovery`, `scrapegraph_client`, …).
- `data/output/` — default enriched workbook.
- `checkpoints/last_run.json` — resume data (`--fresh` to ignore).
- `logs/` — per-run log files.
- `PLAN.md` — phased delivery notes.

## Setup (Windows / PowerShell)

```powershell
cd "C:\Users\Lenovo\Desktop\ScrapeAI"
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Only if you use Playwright (playwright provider or SEARCH_PLAYWRIGHT_FALLBACK):
playwright install chromium
copy .env.example .env
# Edit .env: SCRAPEGRAPH_API_KEY when live extracting; GOOGLE_CSE_* for production search.
```

## Run (recommended wrappers)

**Option A — helper script (sets `PYTHONPATH=src`):**

```powershell
.\run.ps1 --limit 3 --print-summary
```

**Option B — manual:**

```powershell
$env:PYTHONPATH = ".\src"
python -m scrape_ai_workflow --help
```

## Modes (save API credits while building)

By default `.env.example` keeps:

- `DRY_RUN_EXTRACT=true` — **no HTTP** to ScrapeGraph; returns placeholder extraction JSON so the Excel pipeline can be tested end-to-end.
- `MOCK_GOOGLE=true` — **no search**; uses `MOCK_WEBSITE_URL` (default `https://example.com`) as the discovered URL.

### Trial commands

Dry pipeline on first 3 companies (no credits, no search):

```powershell
.\run.ps1 --input ".\apoorva trail sheet.xlsx" --output-xlsx ".\data\output\trial_dry.xlsx" --output-csv ".\data\output\trial_dry.csv" --limit 3 --print-summary
```

When you are ready to burn ScrapeGraph credits (requires real key in `.env`):

```powershell
.\run.ps1 --live-extract --limit 1 --print-summary
```

Live **search** without mock URLs (uses CSE if configured, else DDG):

```powershell
.\run.ps1 --live-google --dry-run-extract --limit 10 --print-summary
```

CLI flags override env for the run:

- `--dry-run-extract` / `--live-extract`
- `--mock-google` / `--live-google`

## ScrapeGraphAI API reference

- Endpoint: `POST https://v2-api.scrapegraphai.com/api/extract`
- Header: `SGAI-APIKEY: <key>`
- Body: `{"url": "...", "prompt": "...", "schema": { ... }}`

The prompt + schema live in `src/scrape_ai_workflow/schema_prompts.py` (edit there if the client changes wording).

## Outputs

- **Excel** columns: `sr_no`, `company_name`, `website_url`, `company_name_extracted`, `email1..3`, `contact1..3`, `status`, `error_detail`, `scraped_at`.
- **`<output>.summary.json`** next to the workbook — counts for quick QA.

## Resume

Re-run the same `--input` and `--checkpoint` paths; completed companies are skipped unless `--fresh`.

## Why not `duckduckgo-search` on PyPI?

Optional third-party wrappers can break when DDG changes. This repo uses **official HTML endpoint + BeautifulSoup** for a controllable fallback you can tune in code.
