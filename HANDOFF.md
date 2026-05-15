# ScrapeAI — Agent Handoff (read this first)

**Last updated:** 2026-05-15 (v2 — Playwright+Bing search)
**Repo:** `git@github.com:Apoorva11122020/ScrapeGraph.git` (branch `master`)  
**Workspace:** `C:\Users\Lenovo\Desktop\ScrapeAI`  

---

## 1. One-line goal

Read company names from client Excel → discover **official website URL** per company → call **ScrapeGraphAI v2 Extract** with client prompt/schema → write **Excel/CSV** with emails/contacts; **every row kept** (failures = blank fields + `status` + `error_detail`).

---

## 2. Client constraints (non-negotiable)

| Constraint | Detail |
|------------|--------|
| Pay only for **ScrapeGraphAI** (for now) | Client does **not** want paid Google Custom Search API billed yet; discuss **later** for ~20k scale. |
| URL discovery scope | Script finds **base website URL** only. "Contact Us" / email priority is in **ScrapeGraph extraction prompt** (`schema_prompts.py`). |
| Trial input | `apoorva trail sheet.xlsx` — **~90 companies**, column `COMPANY NAME`, pandas `header=1` (Excel header row 2). |
| Future scale | **~20,000** companies later — need checkpoint/resume (already built). |
| ScrapeGraph credits | Demo account ~**475 credits**, ~**5 credits/company** — **do not burn** until URL step is acceptable. Keep `DRY_RUN_EXTRACT=true` until URL QA passes. |

---

## 3. What is built (status)

### Package: `src/scrape_ai_workflow/`

| Module | Role |
|--------|------|
| `excel_io.py` | Read sheet; write output columns |
| `pipeline.py` | E2E orchestration, summary JSON, logging; calls `close_browser()` at end |
| `checkpoint.py` | Resume; `row_is_success()` skips only rows with valid URL + ok/mismatch status |
| `google_discovery.py` | URL discovery: **Playwright+Bing** (default), CSE (if keys), DuckDuckGo (legacy fallback) |
| `url_ranking.py` | Score/rank SERP candidates; block directories/social; `MIN_ACCEPT_SCORE=3.0` |
| `search_query.py` | Short query: `"{name} India company website"` (long queries returned empty) |
| `scrapegraph_client.py` | POST Extract API; honors `DRY_RUN_EXTRACT` |
| `schema_prompts.py` | Client extraction prompt + JSON schema |
| `settings.py` | `.env` loading; includes `playwright_search_delay_s` |
| `cli.py` / `__main__.py` | CLI flags |

### Output columns

`sr_no`, `company_name`, `website_url`, `company_name_extracted`, `email1..3`, `contact1..3`, `status`, `error_detail`, `scraped_at`, `url_match_score`

### CLI highlights

```powershell
cd "C:\Users\Lenovo\Desktop\ScrapeAI"
pip install -r requirements.txt
playwright install chromium        # FIRST TIME ONLY — downloads ~130MB browser
$env:PYTHONPATH = ".\src"

# URL only, no ScrapeGraph credits (recommended first step)
python -m scrape_ai_workflow --live-google --urls-only --limit 5 --fresh --print-summary

# Full 90-company URL run
python -m scrape_ai_workflow --live-google --urls-only --fresh --print-summary

# Resume failed URL rows only
python -m scrape_ai_workflow --live-google --urls-only --retry-failed --checkpoint ".\checkpoints\apoorva_urls.json"

# Live extract (needs SCRAPEGRAPH_API_KEY)
python -m scrape_ai_workflow --live-google --live-extract --limit 5 --print-summary
```

---

## 4. Current `.env` (developer machine — do not commit secrets)

```env
SCRAPEGRAPH_API_KEY=          # empty until live extract testing
DRY_RUN_EXTRACT=true
MOCK_GOOGLE=false

# ---- Search provider ----
SEARCH_PROVIDER=playwright_bing   # NEW DEFAULT (was: duckduckgo)
PLAYWRIGHT_SEARCH_DELAY_S=6.0

GOOGLE_CSE_API_KEY=           # empty — client deferred to future scale
GOOGLE_CSE_CX=
CSE_DELAY_S=0.25
```

---

## 5. Search provider — history & current approach

### Why DuckDuckGo was replaced

| Symptom | Cause |
|---------|--------|
| `202 Ratelimit` on DDG HTML/lite endpoints | IP throttled after a few queries |
| `ddg_transport_error` / `ddg_http_error` | Network + rate limits on full 90-row run |
| `ddg_no_results` | Empty SERP, IP throttling pattern |
| `low_confidence` | Results returned but score below `MIN_ACCEPT_SCORE` |

**Results from actual runs:**
- Live DDG full 90: **5** `extract_ok`, **37** `ddg_http_error`, **39** `ddg_transport_error`, **9** `low_confidence`
- Live test 5: **0/5 URLs** — 4× `ddg_no_results`, 1× `low_confidence`

### Current approach: Playwright + Bing (v2)

`SEARCH_PROVIDER=playwright_bing` → `_discover_playwright_bing()` in `google_discovery.py`

**How it works:**
1. Launches a **single headless Chromium** browser (reused across all 90 companies — fast)
2. Navigates to `https://www.bing.com/search?q=...` per company
3. Waits for results, parses `#b_results li.b_algo` (organic results)
4. Passes candidates to `pick_best_url()` in `url_ranking.py`
5. If no results → retries with variant queries (up to 3 variants)
6. Polite 6–8s delay between searches (configurable via `PLAYWRIGHT_SEARCH_DELAY_S`)
7. Blocks images/fonts/media for speed
8. `close_browser()` called at end of pipeline run

**Why Bing (not Google):**
- Google.com → immediate `/sorry/` CAPTCHA (verified in earlier testing)
- Bing is significantly less aggressive with automated browsing
- ~90 companies at 8s/each ≈ **12–15 minutes total**, no rate limit issues expected

**Why NOT DuckDuckGo API library:**
- `duckduckgo-search` library uses Bing backend — same rate limits, without browser control
- Observed ~5% success rate on 90-company run

### Search provider summary

| Provider | Setting | Use case |
|----------|---------|----------|
| `playwright_bing` | **DEFAULT** | 90-company demo — no API keys needed |
| `cse` | `SEARCH_PROVIDER=cse` | 20k production — needs `GOOGLE_CSE_API_KEY` + `GOOGLE_CSE_CX` |
| `auto` | `SEARCH_PROVIDER=auto` | CSE if keys set, else Playwright Bing |
| `duckduckgo` | `SEARCH_PROVIDER=duckduckgo` | Legacy fallback — NOT recommended |

---

## 6. First-time setup on new machine

```powershell
cd "C:\Users\Lenovo\Desktop\ScrapeAI"
git pull origin master
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium          # downloads Chromium browser binary
```

Then copy `.env.example` → `.env` and fill in `SCRAPEGRAPH_API_KEY` when ready.

---

## 7. Recommended next steps (priority order)

### For 90-company demo

**Step 1 — Run URL discovery:**
```powershell
$env:SEARCH_PROVIDER = "playwright_bing"
$env:MOCK_GOOGLE = "false"
python -m scrape_ai_workflow --live-google --urls-only --fresh --print-summary
```

**Step 2 — Review output:**
Open `data/output/apoorva_urls_full.xlsx`, check `website_url` + `url_match_score` columns.  
Manually correct any obvious wrong URLs.

**Step 3 — Run ScrapeGraph extract:**
Set `SCRAPEGRAPH_API_KEY` in `.env`, then:
```powershell
python -m scrape_ai_workflow --live-google --live-extract --limit 5 --print-summary
```
Smoke test with 5 rows, then full sheet.

### For 20k production

- Get client approval for **Google CSE** ($5/1000 queries) or **Brave Search API** (free tier: 1k/month)
- Set `SEARCH_PROVIDER=auto` + `GOOGLE_CSE_API_KEY` + `GOOGLE_CSE_CX` in `.env`
- Keep checkpoint/resume; tune `CSE_DELAY_S`

---

## 8. ScrapeGraph API

- **Endpoint:** `POST https://v2-api.scrapegraphai.com/api/extract`
- **Header:** `SGAI-APIKEY: <key>`
- **Body:** `{"url": "...", "prompt": "...", "schema": {...}}`
- **Client module:** `scrapegraph_client.py`  
- **Prompt/schema:** `schema_prompts.py` — use `build_extraction_prompt(expected_company_name)` per row.

---

## 9. Key paths

| Path | Purpose |
|------|---------|
| `apoorva trail sheet.xlsx` | Trial input (~90 companies) |
| `data/output/` | Outputs + `*.summary.json` |
| `checkpoints/apoorva_urls.json` | URL-run checkpoint |
| `checkpoints/last_run.json` | Default checkpoint |
| `logs/run_*.log` | Per-run logs |
| `.env` | Local secrets (gitignored) |
| `.env.example` | Template |

---

## 10. Git / push notes

- Remote: `origin` → `Apoorva11122020/ScrapeGraph.git`
- Do **not** commit `.env`, API keys, or large client xlsx if gitignored.
- Changed files in v2: `google_discovery.py`, `settings.py`, `pipeline.py`, `cli.py`, `.env.example`, `RUN_COMMANDS.md`, `HANDOFF.md`

---

## 11. Quick verification commands

```powershell
cd "C:\Users\Lenovo\Desktop\ScrapeAI"
$env:PYTHONPATH = ".\src"

# Dry pipeline smoke (no browser, no credits)
python -m scrape_ai_workflow --limit 2 --fresh --print-summary

# Live URL discovery smoke (5 companies via Playwright+Bing)
python -m scrape_ai_workflow --live-google --urls-only --limit 5 --fresh --print-summary

# Inspect output
python -c "import pandas as pd; print(pd.read_excel('data/output/enriched.xlsx')[['company_name','website_url','status']])"
```

---

## 12. Decision log

| Decision | Rationale |
|----------|-----------|
| **Playwright + Bing** for URL discovery (v2) | DDG ~5% success rate on 90-company run; Bing doesn't CAPTCHA like Google |
| Single shared browser instance | Reuse across all rows — faster startup, lower memory |
| Short search queries | Long queries returned empty SERP |
| `url_ranking.py` scoring | First organic link often wrong (directories, unrelated brands) |
| Postpone live ScrapeGraph | Credits precious until URLs trustworthy |
| Defer Google CSE to client future budget | Client wants ScrapeGraph-only billing for now |
| DDG kept as fallback | In case Bing rate-limits in future; set `SEARCH_PROVIDER=duckduckgo` |

---

*End of handoff — start with §5 if debugging search; §6 for new machine setup; §7 for next steps.*


---

## 1. One-line goal

Read company names from client Excel → discover **official website URL** per company → call **ScrapeGraphAI v2 Extract** with client prompt/schema → write **Excel/CSV** with emails/contacts; **every row kept** (failures = blank fields + `status` + `error_detail`).

---

## 2. Client constraints (non-negotiable)

| Constraint | Detail |
|------------|--------|
| Pay only for **ScrapeGraphAI** (for now) | Client does **not** want paid Google Custom Search API billed yet; discuss **later** for ~20k scale. |
| URL discovery scope | Script finds **base website URL** only. “Contact Us” / email priority is in **ScrapeGraph extraction prompt** (`schema_prompts.py`). |
| Trial input | `apoorva trail sheet.xlsx` — **~90 companies**, column `COMPANY NAME`, pandas `header=1` (Excel header row 2). |
| Future scale | **~20,000** companies later — need checkpoint/resume (already built). |
| ScrapeGraph credits | Demo account ~**475 credits**, ~**5 credits/company** — **do not burn** until URL step is acceptable. Keep `DRY_RUN_EXTRACT=true` until URL QA passes. |
| Proposal wording | Client proposal mentioned **Playwright + Selenium** for Google search — **not viable at scale** (CAPTCHA). Free **DuckDuckGo** path was implemented instead; **unreliable** in practice (see §5). |

---

## 3. What is built (status)

### Package: `src/scrape_ai_workflow/`

| Module | Role |
|--------|------|
| `excel_io.py` | Read sheet; write output columns |
| `pipeline.py` | E2E orchestration, summary JSON, logging |
| `checkpoint.py` | Resume; `row_is_success()` skips only rows with valid URL + ok/mismatch status |
| `google_discovery.py` | URL discovery: **CSE** (if keys), else **DuckDuckGo** via `duckduckgo-search` |
| `url_ranking.py` | Score/rank SERP candidates; block directories/social; `MIN_ACCEPT_SCORE=3.0` |
| `search_query.py` | Short query: `"{name} India company website"` (long queries returned empty) |
| `scrapegraph_client.py` | POST Extract API; honors `DRY_RUN_EXTRACT` |
| `schema_prompts.py` | Client extraction prompt + JSON schema |
| `settings.py` | `.env` loading |
| `cli.py` / `__main__.py` | CLI flags |

### Output columns

`sr_no`, `company_name`, `website_url`, `company_name_extracted`, `email1..3`, `contact1..3`, `status`, `error_detail`, `scraped_at`, `url_match_score`

### CLI highlights

```powershell
cd "C:\Users\Lenovo\Desktop\ScrapeAI"
$env:PYTHONPATH = ".\src"
pip install -r requirements.txt

# URL only, no ScrapeGraph credits
python -m scrape_ai_workflow --live-google --urls-only --limit 5 --fresh --print-summary

# Full pipeline dry (mock search + dry extract)
python -m scrape_ai_workflow --limit 3 --print-summary

# Live extract (needs SCRAPEGRAPH_API_KEY, --live-extract)
python -m scrape_ai_workflow --live-google --live-extract --limit 5 --print-summary

# Resume failed URL rows only
python -m scrape_ai_workflow --live-google --urls-only --retry-failed --checkpoint ".\checkpoints\apoorva_urls.json"
```

Also: `run.ps1`, `README.md`, `RUN_COMMANDS.md`, `PLAN.md`.

### What is NOT done / NOT wired

| Item | Status |
|------|--------|
| **Playwright Google search** | `playwright` imported in `google_discovery.py` but **no `_discover_playwright()`** — `SEARCH_PROVIDER=playwright` still falls through to DuckDuckGo. `SEARCH_PLAYWRIGHT_FALLBACK` in settings is **unused**. |
| **Live ScrapeGraph extract on real URLs** | Not run successfully end-to-end on client sheet (API key was empty; URL step blocked first). |
| **Reliable free URL discovery for 90 rows** | **Failed in practice** (~5–10% success on full run). |
| **Excel `website_url` input column** (skip search if pre-filled) | **Not implemented** — good next task for demo hybrid workflow. |
| **Brave Search API** | Discussed as free alternative for 90 demo; **not coded**. |

---

## 4. Current `.env` (developer machine — do not commit secrets)

Typical trial settings (see `.env.example` for full list):

```env
SCRAPEGRAPH_API_KEY=          # empty until live extract testing
DRY_RUN_EXTRACT=true
MOCK_GOOGLE=false
SEARCH_PROVIDER=duckduckgo
DDG_DELAY_S=15
DDG_API_RETRIES=1
DDG_MAX_VARIANTS=1
DDG_RATELIMIT_COOLDOWN_S=120
DDG_USE_HTML_FALLBACK=false
SEARCH_PLAYWRIGHT_FALLBACK=false
GOOGLE_CSE_API_KEY=           # empty — client deferred to future scale
GOOGLE_CSE_CX=
```

---

## 5. Free search path — what went wrong (read before changing code)

### Architecture today

1. `SEARCH_PROVIDER=duckduckgo` → `_discover_duckduckgo()` in `google_discovery.py`
2. Uses library **`duckduckgo-search`** (`DDGS().text(..., backend="bing")`) — often hits `bing.com/search` (not duckduckgo.com HTML).
3. Results passed to `pick_best_url()` in `url_ranking.py` (not “first link wins”).
4. If `GOOGLE_CSE_*` set and `SEARCH_PROVIDER=auto` → CSE first, then DDG fallback.

### Observed failures (from runs + terminal logs)

| Symptom | Cause |
|---------|--------|
| `202 Ratelimit` on `html.duckduckgo.com` / `lite.duckduckgo.com` | Too many HTML/lite requests; IP throttled. **Fix applied:** `DDG_USE_HTML_FALLBACK=false`, fewer variants/retries, longer delay + cooldown. |
| `ddg_transport_error` / `ddg_http_error` | Network + rate limits on full 90-row run. |
| `ddg_no_results` / empty result set | Bing/DDG returned nothing (sometimes first call empty, second works — IP throttling pattern). |
| `low_confidence` | Results returned but score below `MIN_ACCEPT_SCORE` (e.g. news sites for “Sekar Leather”). |
| Wrong URLs (earlier) | First SERP link ≠ official site — **mitigated** by `url_ranking.py`, not eliminated when SERP is garbage. |

### Run results (evidence)

| Run | Output | Result |
|-----|--------|--------|
| Dry mock full 90 | `data/output/apoorva_dry_full.xlsx` | 90 rows, fake `example.com`, `extract_ok` — pipeline only |
| Live DDG full 90 | `data/output/apoorva_urls_full.xlsx` + `.summary.json` | **5** `extract_ok`, **37** `ddg_http_error`, **39** `ddg_transport_error`, **9** `low_confidence` |
| Live test 5 | `data/output/test5.xlsx` | **0/5 URLs** — 4× `ddg_no_results`, 1× `low_confidence` |
| Earlier test 5 | mixed | Some good (`dlinternational.com`, `whitehouse.in`), some bad before scoring fixes |

### Why Playwright/Selenium is not the fix

- **Google.com** via browser → immediate **`/sorry/` CAPTCHA** (tested early in project).
- **Bing via Playwright** ≈ same backend the library already uses; same rate limits, more complexity.
- **Not implemented** in code despite README/CLI mentioning Playwright fallback.

### Paid path (future / production) — already coded

**Google Custom Search Engine (CSE)** — `GOOGLE_CSE_API_KEY` + `GOOGLE_CSE_CX`, `SEARCH_PROVIDER=auto` or `cse`.  
~100 queries/day free, then ~**$5 / 1,000** (~$100 for 20k). Client to approve later.

**Brave Search API** — not in repo; ~1000 free queries/month possible for 90 demo if integrated.

---

## 6. Recommended next steps (priority order)

### For 90-company demo (no CSE budget yet)

**Option A — Most reliable (recommended):**  
1. Add optional input column `website_url` (or separate mapping sheet) — skip discovery when filled.  
2. Manually verify URLs for 90 companies (browser Google).  
3. Run `--urls-only` only for missing rows OR skip straight to extract.  
4. Set `SCRAPEGRAPH_API_KEY`, `DRY_RUN_EXTRACT=false`, `--live-extract --limit 5` smoke, then full sheet.

**Option B — Free auto (fragile):**  
- Run **15 companies per session**, 2–4h gap or mobile hotspot between sessions.  
- `DDG_DELAY_S=25–30`, single variant, no HTML fallback.  
- Manually fix failed rows.

**Option C — Code Brave Search API** for 90 demo (free tier).

### For 20k production

- Get client approval for **Google CSE** (or Brave paid).  
- Set `SEARCH_PROVIDER=auto` + keys.  
- Keep checkpoint/resume; tune `CSE_DELAY_S`.

### Code hygiene (low priority)

- Migrate `duckduckgo-search` → `ddgs` package (rename warning in logs).  
- Implement Playwright **only if** product owner insists — prefer CSE/Brave over google.com scrape.  
- Wire or remove dead `SEARCH_PLAYWRIGHT_FALLBACK` / unused playwright imports.

---

## 7. ScrapeGraph API

- **Endpoint:** `POST https://v2-api.scrapegraphai.com/api/extract`
- **Header:** `SGAI-APIKEY: <key>`
- **Body:** `{"url": "...", "prompt": "...", "schema": {...}}`
- **Client module:** `scrapegraph_client.py`  
- **Prompt/schema:** `schema_prompts.py` — use `build_extraction_prompt(expected_company_name)` per row.

---

## 8. Key paths

| Path | Purpose |
|------|---------|
| `apoorva trail sheet.xlsx` | Trial input |
| `data/output/` | Outputs + `*.summary.json` |
| `checkpoints/apoorva_urls.json` | URL-run checkpoint |
| `checkpoints/last_run.json` | Default checkpoint |
| `logs/run_*.log` | Per-run logs |
| `.env` | Local secrets (gitignored) |
| `.env.example` | Template |

---

## 9. Client messaging (short)

**Demo now:** “URLs verify karke ScrapeGraph se contacts extract — free automated search trial par rate-limit ki wajah se stable nahi.”

**Future scale:** “20k ke liye official Google Search API (chhota cost, ScrapeGraph alag) — production standard.”

**Do not say:** “Playwright fail.” **Say:** “Search automation industry-wide rate-limited; demo hybrid; production mein paid search API.”

---

## 10. Git / push notes

- Remote: `origin` → `Apoorva11122020/ScrapeGraph.git`
- Do **not** commit `.env`, API keys, or large client xlsx if gitignored.
- Uncommitted code changes at handoff time may include: `google_discovery.py`, `search_query.py`, `url_ranking.py`, `settings.py`, `requirements.txt`.

---

## 11. Quick verification commands

```powershell
cd "C:\Users\Lenovo\Desktop\ScrapeAI"
$env:PYTHONPATH = ".\src"

# Dry pipeline smoke
python -m scrape_ai_workflow --limit 2 --fresh --print-summary

# Live URL discovery smoke (expect rate limits if IP hot)
python -m scrape_ai_workflow --live-google --urls-only --limit 3 --fresh --print-summary

# Inspect output
python -c "import pandas as pd; print(pd.read_excel('data/output/test5.xlsx')[['company_name','website_url','status']])"
```

---

## 12. Decision log

| Decision | Rationale |
|----------|-----------|
| DDG library with `backend="bing"` | More stable than html/lite DDG endpoints |
| Short search queries | Long queries returned empty SERP |
| `url_ranking.py` | First organic link often wrong (directories, unrelated brands) |
| Postpone live ScrapeGraph | Credits precious until URLs trustworthy |
| Defer Google CSE to client future budget | Client wants ScrapeGraph-only billing for now |
| HANDOFF.md | Continuity for next agent / developer |

---

*End of handoff — start with §5 if debugging search; §6 if delivering demo.*
