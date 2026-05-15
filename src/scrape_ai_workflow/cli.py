from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from .pipeline import run_pipeline
from .settings import Settings, load_settings


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Excel companies → Google website URL → ScrapeGraphAI Extract → Excel/CSV.",
    )
    p.add_argument(
        "--input",
        type=Path,
        default=Path("apoorva trail sheet.xlsx"),
        help="Input .xlsx path (default: ./apoorva trail sheet.xlsx).",
    )
    p.add_argument(
        "--output-xlsx",
        type=Path,
        default=Path("data/output/enriched.xlsx"),
        help="Output workbook path.",
    )
    p.add_argument("--output-csv", type=Path, default=None, help="Optional CSV output path.")
    p.add_argument(
        "--checkpoint",
        type=Path,
        default=Path("checkpoints/last_run.json"),
        help="Checkpoint JSON for resume (skipped if --fresh).",
    )
    p.add_argument(
        "--log-dir",
        type=Path,
        default=Path("logs"),
        help="Directory for run log files.",
    )
    p.add_argument("--header-row", type=int, default=1, help="0-based pandas header row index (client sheet uses 1).")
    p.add_argument("--limit", type=int, default=None, help="Process only first N data rows (testing).")
    p.add_argument("--checkpoint-every", type=int, default=5, help="Flush checkpoint every N completed rows.")
    p.add_argument("--fresh", action="store_true", help="Ignore existing checkpoint contents.")
    p.add_argument(
        "--retry-failed",
        action="store_true",
        help="Re-run rows without a good website URL; keep rows that already succeeded.",
    )
    p.add_argument(
        "--urls-only",
        action="store_true",
        help="Only discover website URLs (no ScrapeGraph extract / no credits).",
    )

    g = p.add_mutually_exclusive_group()
    g.add_argument("--dry-run-extract", action="store_true", help="Force DRY_RUN_EXTRACT=true (no credits).")
    g.add_argument("--live-extract", action="store_true", help="Force live ScrapeGraph calls (needs API key).")

    g2 = p.add_mutually_exclusive_group()
    g2.add_argument("--mock-google", action="store_true", help="Force MOCK_GOOGLE=true.")
    g2.add_argument("--live-google", action="store_true", help="Force MOCK_GOOGLE=false (Playwright).")

    p.add_argument("--print-summary", action="store_true", help="Print summary JSON to stdout.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    settings: Settings = load_settings()

    if args.dry_run_extract:
        settings = replace(settings, dry_run_extract=True)
    elif args.live_extract:
        settings = replace(settings, dry_run_extract=False)

    if args.mock_google:
        settings = replace(settings, mock_google=True)
    elif args.live_google:
        settings = replace(settings, mock_google=False)

    if not settings.dry_run_extract and not settings.scrapegraph_api_key:
        print(
            "ERROR: live extract enabled but SCRAPEGRAPH_API_KEY is missing. "
            "Use .env / environment, or pass --dry-run-extract.",
            file=sys.stderr,
        )
        return 2

    if not settings.mock_google:
        prov = settings.search_provider.strip().lower()
        if prov in ("google", "playwright", "bing"):
            prov = "playwright_bing"
        cse_ok = bool(
            (settings.google_cse_api_key or "").strip() and (settings.google_cse_cx or "").strip()
        )
        if prov == "cse" and not cse_ok:
            print(
                "WARN: SEARCH_PROVIDER=cse but GOOGLE_CSE_API_KEY / GOOGLE_CSE_CX missing.",
                file=sys.stderr,
            )
        if prov in ("auto", "") and cse_ok:
            print(
                "INFO: SEARCH_PROVIDER=auto — primary search is Google CSE, fallback Playwright+Bing.",
                file=sys.stderr,
            )
        elif prov == "cse" and cse_ok:
            print("INFO: Using Google Programmable Search only.", file=sys.stderr)
        elif prov == "playwright_bing":
            print(
                "INFO: Using Playwright + Bing search (reliable, no rate limits).",
                file=sys.stderr,
            )
        else:
            print(
                f"INFO: Using search provider: {prov}",
                file=sys.stderr,
            )

    summary = run_pipeline(
        input_path=args.input,
        output_xlsx=args.output_xlsx,
        output_csv=args.output_csv,
        checkpoint_path=args.checkpoint,
        log_dir=args.log_dir,
        settings=settings,
        header_row=args.header_row,
        limit=args.limit,
        checkpoint_every=args.checkpoint_every,
        fresh=args.fresh,
        retry_failed=args.retry_failed,
        urls_only=args.urls_only,
    )
    if args.print_summary:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
