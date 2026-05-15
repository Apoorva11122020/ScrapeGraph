# Run Commands

## First-time setup

```powershell
cd "C:\Users\Lenovo\Desktop\ScrapeAI"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

---

## Find URLs (90 companies)

```powershell
$env:PYTHONPATH = ".\src"
$env:MOCK_GOOGLE = "false"
python -m scrape_ai_workflow --live-google --urls-only --fresh --print-summary
```

- Batch mode: 5 companies → 2 min cooldown → next 5
- Total time: ~45-55 min
- Output: `data\output\enriched.xlsx`

---

## Retry failed only

```powershell
$env:PYTHONPATH = ".\src"
$env:MOCK_GOOGLE = "false"
python -m scrape_ai_workflow --live-google --urls-only --retry-failed --print-summary
```

---

## Quick test (5 companies)

```powershell
$env:PYTHONPATH = ".\src"
$env:MOCK_GOOGLE = "false"
python -m scrape_ai_workflow --live-google --urls-only --limit 5 --fresh --print-summary
```

---

## ScrapeGraph Extract (after URLs are verified)

```powershell
$env:PYTHONPATH = ".\src"
$env:MOCK_GOOGLE = "false"
$env:DRY_RUN_EXTRACT = "false"
$env:SCRAPEGRAPH_API_KEY = "sgai-your-key"
python -m scrape_ai_workflow --live-google --live-extract --limit 5 --print-summary
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| CAPTCHA | Wait 5 min, retry. Or use proxy: `PLAYWRIGHT_PROXY_SERVER` |
| PermissionError xlsx | Close Excel file first |
| Playwright not found | `pip install playwright && playwright install chromium` |
| No output in terminal | Already shows progress step-by-step |
