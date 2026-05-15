# ScrapeAI — Handoff Document

**Last updated:** 2026-05-15 (v4 — Playwright-only, final)  
**Repo:** `github.com/Apoorva11122020/ScrapeGraph` (branch `master`)

---

## 1. Goal

Read ~90 company names from Excel → find official website URL → later extract emails/contacts using ScrapeGraphAI.

---

## 2. How it works

```
Excel (90 companies)
    │
    ▼
Playwright (headless Chromium browser)
    → searches Google.com (like a real user)
    → parses organic results from HTML
    → ranks URLs with url_ranking.py
    │
    ├── Batch mode: 5 companies, then 2 min cooldown
    ├── 3 query variants per company if needed
    ├── CAPTCHA detection + auto-wait
    │
    ▼
Output: Excel + CSV + checkpoint JSON
```

---

## 3. Package: `src/scrape_ai_workflow/`

| Module | Purpose |
|--------|---------|
| `google_discovery.py` | Playwright + Google search (only method) |
| `url_ranking.py` | Score/rank URLs, block directories |
| `search_query.py` | Query builder (name → name company → name official website) |
| `pipeline.py` | Orchestration, batch mode, progress prints |
| `checkpoint.py` | Resume interrupted runs |
| `excel_io.py` | Read/write Excel |
| `scrapegraph_client.py` | ScrapeGraphAI API |
| `schema_prompts.py` | Extraction prompt/schema |
| `settings.py` | .env config (minimal) |
| `cli.py` | CLI interface |

---

## 4. Setup

```powershell
cd "C:\Users\Lenovo\Desktop\ScrapeAI"
pip install -r requirements.txt
playwright install chromium
```

---

## 5. Run

```powershell
$env:PYTHONPATH = ".\src"
$env:MOCK_GOOGLE = "false"
python -m scrape_ai_workflow --live-google --urls-only --fresh --print-summary
```

---

## 6. Edge cases handled

| Scenario | How handled |
|----------|-------------|
| Google CAPTCHA | Detects, waits 3 min, warns user |
| No results for query 1 | Tries 2 more query variants |
| Rate limit | Batch mode (5 companies → 2 min gap) |
| Blocked domain in results | 50+ patterns blocked (social, directories) |
| Duplicate domains | Deduplication in result parsing |
| Browser crash | Auto-relaunches |
| Cookie consent popup | Auto-dismisses |
| Empty company name | Returns error, doesn't crash |
| Excel file open | Shows PermissionError (user must close file) |
| Interrupted run | Checkpoint saves every 5 rows — resume with `--retry-failed` |

---

## 7. Config (.env)

Only 3 settings needed:
```
MOCK_GOOGLE=false              # must be false for real searches
DRY_RUN_EXTRACT=true           # true = don't burn ScrapeGraph credits
SCRAPEGRAPH_API_KEY=           # fill when ready for extract step
```

Optional: `PLAYWRIGHT_PROXY_SERVER=http://user:pass@proxy:port`

---

## 8. Dependencies

```
pandas, openpyxl     — Excel
httpx                — HTTP client
python-dotenv        — .env
beautifulsoup4       — HTML parsing
playwright           — headless browser (Chromium)
```

No googlesearch-python, no duckduckgo-search — just Playwright.

---

## 9. For 20K scale (future)

Playwright won't work for 20K (CAPTCHA guaranteed). Options:
- SerpAPI ($50/month) — Google results via API
- Serper.dev ($50/month) — same
- Google CSE ($5/1000 queries = $100 for 20K)

---

*End of handoff.*
