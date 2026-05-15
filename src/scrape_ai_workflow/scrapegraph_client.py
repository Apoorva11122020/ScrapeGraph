from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .schema_prompts import OUTPUT_JSON_SCHEMA, build_extraction_prompt
from .settings import Settings

log = logging.getLogger(__name__)

DRY_RUN_SAMPLE: dict[str, str] = {
    "company_name": "Demo Co (dry-run)",
    "email1": "demo@example.com",
    "email2": "",
    "email3": "",
    "contact1": "9999999999",
    "contact2": "",
    "contact3": "",
}


@dataclass(frozen=True)
class ExtractOutcome:
    ok: bool
    data: dict[str, str]
    http_status: int | None
    error_detail: str
    request_id: str | None


def _normalize_extract_json(payload: dict[str, Any]) -> dict[str, str]:
    keys = ["company_name", "email1", "email2", "email3", "contact1", "contact2", "contact3"]
    out: dict[str, str] = {}
    inner = payload.get("json")
    if not isinstance(inner, dict):
        inner = {}
    for k in keys:
        v = inner.get(k, "")
        out[k] = "" if v is None else str(v).strip()
    return out


def call_extract(
    website_url: str,
    settings: Settings,
    *,
    expected_company_name: str = "",
    prompt: str | None = None,
    schema: dict[str, Any] | None = None,
    timeout_s: float = 120.0,
    max_retries: int = 2,
) -> ExtractOutcome:
    """
    Call ScrapeGraphAI v2 Extract. Honors DRY_RUN_EXTRACT (no HTTP, no credits).
    Retries only on transport errors and HTTP 5xx.
    """
    sch = schema if schema is not None else OUTPUT_JSON_SCHEMA
    effective_prompt = prompt if prompt is not None else build_extraction_prompt(expected_company_name)

    if settings.dry_run_extract:
        data = {k: "" for k in DRY_RUN_SAMPLE}
        data["company_name"] = expected_company_name or "Unknown"
        return ExtractOutcome(True, data, None, "", None)

    if not settings.scrapegraph_api_key:
        return ExtractOutcome(False, {}, None, "missing_api_key", None)

    body = {"url": website_url, "prompt": effective_prompt, "schema": sch}
    headers = {
        "SGAI-APIKEY": settings.scrapegraph_api_key,
        "Content-Type": "application/json",
    }

    last_err = ""
    for attempt in range(max_retries + 1):
        try:
            with httpx.Client(timeout=timeout_s) as client:
                r = client.post(settings.scrapegraph_extract_url, json=body, headers=headers)
            if r.status_code in (500, 502, 503, 504) and attempt < max_retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            rid = None
            try:
                js = r.json()
                rid = js.get("id") if isinstance(js, dict) else None
            except Exception:
                js = {}

            if r.status_code == 200 and isinstance(js, dict):
                data = _normalize_extract_json(js)
                return ExtractOutcome(True, data, 200, "", str(rid) if rid else None)

            detail = ""
            if isinstance(js, dict):
                detail = str(js.get("error") or js.get("message") or js)
            else:
                detail = r.text[:500]
            last_err = f"http_{r.status_code}: {detail}"
            if r.status_code in (429, 402, 401, 403, 400):
                break
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last_err = f"transport: {e}"
            if attempt < max_retries:
                time.sleep(1.5 * (attempt + 1))
                continue
        break

    log.warning("Extract failed for %s: %s", website_url, last_err)
    return ExtractOutcome(False, {}, None, last_err, None)
