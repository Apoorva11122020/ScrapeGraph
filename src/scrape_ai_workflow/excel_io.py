from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def read_company_sheet(path: Path | str, *, header_row: int = 1) -> pd.DataFrame:
    """
    Read client workbook. Default header_row=1 matches 'apoorva trail sheet.xlsx'
    (row 0 blank, row 1 column titles, data from row 2).
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(p)
    df = pd.read_excel(p, header=header_row, engine="openpyxl")
    # Normalize expected columns
    cols = {c: str(c).strip() for c in df.columns}
    df.rename(columns=cols, inplace=True)
    if "COMPANY NAME" not in df.columns:
        raise ValueError(
            f"Expected a 'COMPANY NAME' column after header_row={header_row}. "
            f"Found columns: {list(df.columns)}"
        )
    if "SR NO" not in df.columns:
        raise ValueError(f"Expected 'SR NO' column. Found: {list(df.columns)}")
    return df


def build_output_row(
    *,
    sr_no: Any,
    company_name: str,
    website_url: str,
    extracted: dict[str, str],
    status: str,
    error_detail: str,
    scraped_at: str,
    url_match_score: str = "",
) -> dict[str, Any]:
    """Single result row for Excel/CSV (always emit, even on failure)."""
    return {
        "sr_no": sr_no,
        "company_name": company_name,
        "website_url": website_url,
        "url_match_score": url_match_score,
        "company_name_extracted": extracted.get("company_name", ""),
        "email1": extracted.get("email1", ""),
        "email2": extracted.get("email2", ""),
        "email3": extracted.get("email3", ""),
        "contact1": extracted.get("contact1", ""),
        "contact2": extracted.get("contact2", ""),
        "contact3": extracted.get("contact3", ""),
        "status": status,
        "error_detail": error_detail,
        "scraped_at": scraped_at,
    }


def write_outputs(rows: list[dict[str, Any]], xlsx_path: Path, csv_path: Path | None) -> None:
    df = pd.DataFrame(rows)
    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(xlsx_path, index=False, engine="openpyxl")
    if csv_path is not None:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(csv_path, index=False, encoding="utf-8")
