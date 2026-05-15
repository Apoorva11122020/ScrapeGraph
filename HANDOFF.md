# ScrapeAI — Handoff Document

**Last updated:** 2026-05-15 (v3 — googlesearch-python)  
**Repo:** `github.com/Apoorva11122020/ScrapeGraph` (branch `master`)

---

## 1. Goal

Read **~90 company names** from Excel → find **official website URL** via Google Search → later extract emails/contacts using **ScrapeGraphAI**.

---

## 2. Architecture (v3)

```
Excel (90 companies)
    │
    ▼
googlesearch-python (FREE, no API key)
    │ searches Google.com directly
    │ 10s delay between searches
    ▼
url_ranking.py (score & pick best URL)
    │
    ▼ [if rate-limited]
Playwright + Google (headless browser fallback)
    │
    ▼
Output: Excel + CSV + checkpoint JSON
    │
    ▼ [later]
ScrapeGraphAI Extract (emails, contacts)
    │
    ▼
Final Excel with all data
```

---

## 3. Package structure: `src/scrape_ai_workflow/`

| Module | Role |
|--------|------|
| `google_discovery.py` | URL discovery: googlesearch-python (primary) + Playwright (fallback) |
| `url_ranking.py` | Score/rank URLs; block directories/social media |
| `search_query.py` | Query builder: `"{name} website"`, variants |
| `pipeline.py` | End-to-end orchestration with progress prints |
| `checkpoint.py` | Resume interrupted runs |
| `excel_io.py` | Read input sheet, write output Excel/CSV |
| `scrapegraph_client.py` | ScrapeGraphAI Extract API client |
| `schema_prompts.py` | Extraction prompt + JSON schema |
| `settings.py` | `.env` configuration loading |
| `cli.py` / `__main__.py` | CLI interface |

---

## 4. How URL discovery works

### Primary: `googlesearch-python`
- **Free**, no API key, no signup
- Searches Google.com via HTTP (like a browser)
- Returns list of URLs → filtered → ranked by `pick_best_url()`
- 10-second delay between searches (configurable)
- If rate limited (HTTP 429) → waits 45-90s then retries

### Fallback: Playwright + Google
- If primary fails → launches headless Chromium
- Searches Google, parses HTML
- Handles different result layouts
- Needs: `playwright install chromium` (one-time)

### URL Ranking (`url_ranking.py`)
- Blocks directories (indiamart, justdial, linkedin, etc.)
- Scores by domain-name match to company name
- `MIN_ACCEPT_SCORE = 3.0`
- If score too low → still picks first result but marks as `low_confidence_picked`

---

## 5. Setup (new machine)

```powershell
cd "C:\Users\Lenovo\Desktop\ScrapeAI"
git pull origin master
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium              # one-time, ~130MB
```

Copy `.env.example` → `.env`:
```env
MOCK_GOOGLE=false
DRY_RUN_EXTRACT=true
GOOGLE_SEARCH_DELAY_S=10
USE_PLAYWRIGHT_FALLBACK=true
```

---

## 6. Running

### Quick test (5 companies):
```powershell
$env:PYTHONPATH = ".\src"
$env:MOCK_GOOGLE = "false"
python -m scrape_ai_workflow --live-google --urls-only --limit 5 --fresh --print-summary
```

### Full 90-company URL run:
```powershell
python -m scrape_ai_workflow --live-google --urls-only --fresh --print-summary
```

### Expected terminal output:
```
INFO: Using Google Search (googlesearch-python) — free, no API key.
INFO: Playwright fallback enabled (if Google rate-limits).

=======================================================
  🚀 Starting pipeline: 5 companies to process
=======================================================

[1/5] 🏢 Company: DL International
  🌐 Google: 'DL International website'
  📋 Results: 10 raw → 6 usable
  ✅ URL: https://dlinternational.com  (score=7.2)

[2/5] 🏢 Company: JMR Apprals
  🌐 Google: 'JMR Apprals website'
  📋 Results: 8 raw → 5 usable
  ✅ URL: https://jmrapprals.com  (score=6.1)
...
=======================================================
  🏁 DONE! 5 rows written.
  📊 Stats: {'url_found': 4, 'low_confidence': 1}
  📁 Output: data\output\enriched.xlsx
=======================================================
```

---

## 7. Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `MOCK_GOOGLE` | `true` | `false` = real Google searches |
| `GOOGLE_SEARCH_DELAY_S` | `10` | Seconds between searches (keep 8-12) |
| `USE_PLAYWRIGHT_FALLBACK` | `true` | Use browser if Google rate-limits |
| `DRY_RUN_EXTRACT` | `true` | `false` = call ScrapeGraphAI |
| `SCRAPEGRAPH_API_KEY` | empty | Needed for extract step |

---

## 8. What changed (version history)

| Version | Approach | Result |
|---------|----------|--------|
| v1 | DuckDuckGo API (`duckduckgo-search`) | ~5% success, rate limited |
| v2 | Playwright + Bing | 0% — Bing returned empty HTML to headless browser |
| **v3** | **googlesearch-python + Playwright fallback** | ✅ Expected to work (Google returns results) |

---

## 9. Key paths

| Path | Purpose |
|------|---------|
| `apoorva trail sheet.xlsx` | Input (~90 companies, header row 2) |
| `data/output/` | Output Excel/CSV + summary JSON |
| `checkpoints/` | Resume state |
| `logs/` | Run logs |
| `.env` | Configuration (gitignored) |
| `.env.example` | Template |

---

## 10. Next steps

1. **Run URL discovery** on 90 companies → verify output
2. **Manual review** of URLs in Excel (fix any wrong ones)
3. **ScrapeGraph extract** — set API key, `--live-extract --limit 5` then full
4. **20K scale** — switch to Google CSE API ($5/1000 queries)

---

## 11. Important notes

- **Don't close Excel** while script is running (PermissionError)
- **Don't Ctrl+C** during a search (wait for it to finish naturally)
- If rate limited: increase `GOOGLE_SEARCH_DELAY_S=15` and retry
- Checkpoint auto-saves every 5 rows — safe to interrupt between companies
- `--retry-failed` re-processes only failed rows (keeps successful ones)

---

## 12. Dependencies

```
pandas, openpyxl       — Excel read/write
httpx                  — HTTP client
python-dotenv          — .env loading
beautifulsoup4         — HTML parsing
googlesearch-python    — Google Search (FREE, primary)
playwright             — Headless browser (fallback)
```

---

*End of handoff.*
