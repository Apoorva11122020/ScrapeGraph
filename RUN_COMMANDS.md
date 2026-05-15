# Manual run commands (PowerShell)

Project folder:

```powershell
cd "C:\Users\Lenovo\Desktop\ScrapeAI"
.\.venv\Scripts\Activate.ps1   # agar venv hai
pip install -r requirements.txt
$env:PYTHONPATH = ".\src"
```

## 1) Sirf URLs dhoondho (ScrapeGraph credits nahi lagenge)

Pehle yahi chalao — output check karo, phir extract.

```powershell
$env:SEARCH_PROVIDER = "duckduckgo"
$env:DDG_DELAY_S = "5"
$env:MOCK_GOOGLE = "false"
$env:DDG_USE_HTML_FALLBACK = "false"

python -m scrape_ai_workflow `
  --input ".\apoorva trail sheet.xlsx" `
  --output-xlsx ".\data\output\apoorva_urls_full.xlsx" `
  --output-csv ".\data\output\apoorva_urls_full.csv" `
  --checkpoint ".\checkpoints\apoorva_urls.json" `
  --live-google `
  --urls-only `
  --fresh `
  --checkpoint-every 5 `
  --print-summary
```

**~90 companies × 5 sec delay ≈ 8–12 min.** Internet stable rakho.

## 2) Failed URLs dubara try (pehli run ke baad)

Jo rows blank / `url_failed` thi, sirf unhe dubara:

```powershell
python -m scrape_ai_workflow `
  --input ".\apoorva trail sheet.xlsx" `
  --output-xlsx ".\data\output\apoorva_urls_full.xlsx" `
  --output-csv ".\data\output\apoorva_urls_full.csv" `
  --checkpoint ".\checkpoints\apoorva_urls.json" `
  --live-google `
  --urls-only `
  --retry-failed `
  --checkpoint-every 5 `
  --print-summary
```

(`--fresh` mat lagana — successful URLs skip ho jayengi.)

## 3) ScrapeGraph extract (jab URLs theek hon)

`.env` mein `SCRAPEGRAPH_API_KEY` daalo, phir:

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

Pehle `--limit 5`, phir poori sheet.

## Output columns

| Column | Meaning |
|--------|---------|
| `website_url` | Discovered site |
| `url_match_score` | Ranking score (higher = better match) |
| `status` | `url_found` / `ok` / `url_failed:...` / `name_mismatch_review` |
| `company_name_extracted` | Site se nikla naam (sheet se compare karo) |

## Tips

- Galat URL se bachne ke liye score threshold hai — agar match weak ho to row **blank** rahegi (`low_confidence`), manual review ke liye.
- Rate limit aaye to `DDG_DELAY_S=6` ya `7` karke `--retry-failed` chalao.
