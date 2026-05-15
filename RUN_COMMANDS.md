# Run Commands

## First-time setup (one time only)

```powershell
cd "C:\Users\Lenovo\Desktop\ScrapeAI"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium          # downloads browser for fallback (~130MB)
```

Copy `.env.example` → `.env` (edit values as needed).

---

## 1) Find URLs only (no ScrapeGraph credits)

```powershell
cd "C:\Users\Lenovo\Desktop\ScrapeAI"
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = ".\src"
$env:MOCK_GOOGLE = "false"

python -m scrape_ai_workflow `
  --input ".\apoorva trail sheet.xlsx" `
  --output-xlsx ".\data\output\apoorva_urls.xlsx" `
  --output-csv ".\data\output\apoorva_urls.csv" `
  --checkpoint ".\checkpoints\apoorva_urls.json" `
  --live-google `
  --urls-only `
  --fresh `
  --checkpoint-every 5 `
  --print-summary
```

**~90 companies × 10-12 sec = ~15-20 min.** Keep internet stable.

---

## 2) Retry failed URLs (after first run)

```powershell
python -m scrape_ai_workflow `
  --input ".\apoorva trail sheet.xlsx" `
  --output-xlsx ".\data\output\apoorva_urls.xlsx" `
  --output-csv ".\data\output\apoorva_urls.csv" `
  --checkpoint ".\checkpoints\apoorva_urls.json" `
  --live-google `
  --urls-only `
  --retry-failed `
  --checkpoint-every 5 `
  --print-summary
```

(Don't use `--fresh` — successful URLs will be kept.)

---

## 3) ScrapeGraph Extract (after URLs are verified)

Set `SCRAPEGRAPH_API_KEY` in `.env`, then:

```powershell
$env:DRY_RUN_EXTRACT = "false"

python -m scrape_ai_workflow `
  --input ".\apoorva trail sheet.xlsx" `
  --output-xlsx ".\data\output\apoorva_final.xlsx" `
  --output-csv ".\data\output\apoorva_final.csv" `
  --checkpoint ".\checkpoints\apoorva_final.json" `
  --live-google `
  --live-extract `
  --limit 5 `
  --print-summary
```

Test with `--limit 5` first, then full sheet.

---

## Quick test (5 companies)

```powershell
$env:PYTHONPATH = ".\src"
$env:MOCK_GOOGLE = "false"
python -m scrape_ai_workflow --live-google --urls-only --limit 5 --fresh --print-summary
```

---

## How it works

1. **googlesearch-python** searches Google (free, no API key)
2. Results ranked by `url_ranking.py` (blocks directories, social media)
3. If Google rate-limits → **Playwright headless browser** fallback
4. 10 sec delay between searches (configurable via `GOOGLE_SEARCH_DELAY_S`)
5. Checkpoint saves progress — resume if interrupted

---

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `MOCK_GOOGLE` | `true` | Set `false` for real searches |
| `GOOGLE_SEARCH_DELAY_S` | `10` | Seconds between searches |
| `USE_PLAYWRIGHT_FALLBACK` | `true` | Use browser if Google blocks |
| `DRY_RUN_EXTRACT` | `true` | Set `false` to use ScrapeGraph |
| `SCRAPEGRAPH_API_KEY` | empty | Required for extract step |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `googlesearch-python not installed` | `pip install googlesearch-python` |
| Rate limited (429) | Increase `GOOGLE_SEARCH_DELAY_S=15` and retry |
| CAPTCHA on Playwright | Wait 30 min, try again (rare for 90 companies) |
| `PermissionError .xlsx` | Close the Excel file before running |
| No output in terminal | Already fixed — shows step-by-step progress |
