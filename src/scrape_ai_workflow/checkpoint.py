from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def row_key(sr_no: Any, company_name: str) -> str:
    """Stable key for checkpointing (pandas ints / numpy scalars → plain strings)."""
    c = " ".join(str(company_name).split()).strip().casefold()
    if sr_no is None or (isinstance(sr_no, float) and str(sr_no) == "nan"):
        s = ""
    else:
        s = str(sr_no).strip()
    return f"{s}::{c}"


def row_is_success(row: dict[str, Any]) -> bool:
    """
    Rows to skip on resume: valid website URL and no hard failure.
    Failed URL lookups and bad URLs are re-tried.
    """
    status = str(row.get("status") or "")
    url = str(row.get("website_url") or "").strip()
    if not url or not url.startswith("http"):
        return False
    if status == "ok":
        return True
    if status == "name_mismatch_review":
        return True
    return False


def load_checkpoint(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {"rows": {}}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if "rows" not in data or not isinstance(data["rows"], dict):
        data["rows"] = {}
    return data


def save_checkpoint(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    tmp.replace(path)


def merge_rows_into_checkpoint(cp: dict[str, Any], row: dict[str, Any]) -> None:
    key = row_key(row["sr_no"], row["company_name"])
    cp["rows"][key] = row
