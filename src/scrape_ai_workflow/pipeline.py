from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .checkpoint import load_checkpoint, merge_rows_into_checkpoint, row_is_success, row_key, save_checkpoint
from .excel_io import build_output_row, read_company_sheet, write_outputs
from .google_discovery import close_browser, discover_official_website
from .scrapegraph_client import call_extract
from .settings import Settings
from .url_ranking import names_likely_match

log = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def configure_logging(log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.log"
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(fh)
    return log_path


def run_pipeline(
    *,
    input_path: Path,
    output_xlsx: Path,
    output_csv: Path | None,
    checkpoint_path: Path | None,
    log_dir: Path,
    settings: Settings,
    header_row: int = 1,
    limit: int | None = None,
    checkpoint_every: int = 5,
    fresh: bool = False,
    retry_failed: bool = False,
    urls_only: bool = False,
) -> dict[str, Any]:
    """
    End-to-end processing. Writes Excel (and optional CSV), checkpoint JSON, summary JSON.
    """
    log_file = configure_logging(log_dir)
    df = read_company_sheet(input_path, header_row=header_row)

    cp: dict[str, Any] = {"input_path": str(input_path.resolve()), "rows": {}}
    if checkpoint_path and not fresh:
        prev = load_checkpoint(checkpoint_path)
        if prev.get("input_path") == cp["input_path"]:
            cp = prev
        else:
            log.warning("Checkpoint input_path mismatch; starting fresh checkpoint data.")
            cp["rows"] = {}

    rows_out: list[dict[str, Any]] = []
    stats: Counter[str] = Counter()

    n = len(df)
    if limit is not None:
        n = min(n, max(limit, 0))

    print(f"\n{'='*55}", flush=True)
    print(f"  🚀 Starting pipeline: {n} companies to process", flush=True)
    print(f"  📦 Batch mode: 5 companies → 2 min cooldown", flush=True)
    print(f"  ⏱️  Estimated time: ~{(n // 5 + 1) * 2 + n * 0.2:.0f} min", flush=True)
    print(f"{'='*55}", flush=True)

    batch_size = 5
    batch_cooldown_s = 120  # 2 minutes between batches
    searches_in_batch = 0  # track actual searches (not skips)

    for i in range(n):
        r = df.iloc[i]
        sr_no = r.get("SR NO")
        company = r.get("COMPANY NAME")
        company_s = "" if company is None or (isinstance(company, float) and str(company) == "nan") else str(company).strip()

        key = row_key(sr_no, company_s)
        if checkpoint_path and not fresh and key in cp.get("rows", {}):
            prev = cp["rows"][key]
            if row_is_success(prev):
                rows_out.append(prev)
                stats["skipped_checkpoint"] += 1
                print(f"\n[{i+1}/{n}] ⏭️  SKIP (checkpoint): {company_s}", flush=True)
                continue

        # Batch cooldown: after every 5 ACTUAL searches, wait 2 min
        if searches_in_batch >= batch_size:
            print(f"\n  ⏸️  Batch cooldown: waiting 2 minutes to avoid rate limit...", flush=True)
            import time as _time
            for remaining in range(batch_cooldown_s, 0, -10):
                print(f"      ⏳ {remaining}s remaining...", flush=True)
                _time.sleep(min(10, remaining))
            print(f"  ▶️  Resuming searches!", flush=True)
            searches_in_batch = 0

        print(f"\n[{i+1}/{n}] 🏢 Company: {company_s}", flush=True)
        scraped_at = _utc_now_iso()
        g = discover_official_website(company_s, settings)
        searches_in_batch += 1
        website = g.url or ""
        url_score = ""
        if g.detail and "score=" in g.detail:
            for part in g.detail.split(";"):
                if "score=" in part:
                    url_score = part.strip().replace("score=", "")
                    break
        if not website:
            print(f"  ❌ URL failed: {g.status} — {g.detail}", flush=True)
            row = build_output_row(
                sr_no=sr_no,
                company_name=company_s,
                website_url="",
                extracted={},
                status=f"url_failed:{g.status}",
                error_detail=g.detail,
                scraped_at=scraped_at,
                url_match_score=url_score,
            )
            stats[g.status] += 1
        elif urls_only:
            print(f"  ✅ URL saved: {website}", flush=True)
            row = build_output_row(
                sr_no=sr_no,
                company_name=company_s,
                website_url=website,
                extracted={},
                status="url_found",
                error_detail=g.detail,
                scraped_at=scraped_at,
                url_match_score=url_score,
            )
            stats["url_found"] += 1
        else:
            ex = call_extract(
                website,
                settings,
                expected_company_name=company_s,
            )
            if ex.ok:
                extracted_name = ex.data.get("company_name", "")
                if not names_likely_match(company_s, extracted_name):
                    status = "name_mismatch_review"
                    stats["name_mismatch_review"] += 1
                else:
                    status = "ok"
                    stats["extract_ok"] += 1
                row = build_output_row(
                    sr_no=sr_no,
                    company_name=company_s,
                    website_url=website,
                    extracted=ex.data,
                    status=status,
                    error_detail="" if status == "ok" else f"sheet={company_s!r} site={extracted_name!r}",
                    scraped_at=scraped_at,
                    url_match_score=url_score,
                )
            else:
                row = build_output_row(
                    sr_no=sr_no,
                    company_name=company_s,
                    website_url=website,
                    extracted=ex.data,
                    status="extract_failed",
                    error_detail=ex.error_detail,
                    scraped_at=scraped_at,
                    url_match_score=url_score,
                )
                stats["extract_failed"] += 1

        rows_out.append(row)
        merge_rows_into_checkpoint(cp, row)

        if checkpoint_path and (len(rows_out) % checkpoint_every == 0):
            save_checkpoint(checkpoint_path, cp)

    if checkpoint_path:
        save_checkpoint(checkpoint_path, cp)

    # Close shared Playwright browser
    close_browser()

    write_outputs(rows_out, output_xlsx, output_csv)

    print(f"\n{'='*55}", flush=True)
    print(f"  🏁 DONE! {len(rows_out)} rows written.", flush=True)
    print(f"  📊 Stats: {dict(stats)}", flush=True)
    print(f"  📁 Output: {output_xlsx}", flush=True)
    print(f"{'='*55}\n", flush=True)

    summary = {
        "generated_at_utc": _utc_now_iso(),
        "input_path": str(input_path.resolve()),
        "output_xlsx": str(output_xlsx.resolve()),
        "output_csv": str(output_csv.resolve()) if output_csv else None,
        "checkpoint_path": str(checkpoint_path.resolve()) if checkpoint_path else None,
        "log_path": str(log_file.resolve()),
        "rows_written": len(rows_out),
        "counts": dict(stats),
        "flags": {
            "dry_run_extract": settings.dry_run_extract,
            "mock_google": settings.mock_google,
        },
    }
    summary_path = output_xlsx.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Wrote summary: %s", summary_path)
    return summary
