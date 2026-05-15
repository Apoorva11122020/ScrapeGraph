from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    """Runtime configuration from environment (and optional CLI overrides)."""

    scrapegraph_api_key: str | None
    scrapegraph_extract_url: str
    dry_run_extract: bool
    mock_google: bool
    mock_website_url: str | None
    google_delay_min_s: float
    google_delay_max_s: float
    playwright_proxy_server: str | None
    search_provider: str  # auto | cse | duckduckgo | playwright | google (alias)
    google_cse_api_key: str | None
    google_cse_cx: str | None
    search_playwright_fallback: bool
    cse_delay_s: float
    ddg_delay_s: float
    ddg_api_retries: int
    ddg_use_html_fallback: bool
    ddg_ratelimit_cooldown_s: float
    ddg_max_variants: int


def load_settings() -> Settings:
    load_dotenv()
    _mock_url = os.getenv("MOCK_WEBSITE_URL")
    if _mock_url is None:
        mock_url: str | None = "https://example.com"
    else:
        mock_url = _mock_url.strip() or None

    return Settings(
        scrapegraph_api_key=os.getenv("SCRAPEGRAPH_API_KEY") or None,
        scrapegraph_extract_url=os.getenv(
            "SCRAPEGRAPH_EXTRACT_URL", "https://v2-api.scrapegraphai.com/api/extract"
        ),
        dry_run_extract=_bool_env("DRY_RUN_EXTRACT", default=True),
        mock_google=_bool_env("MOCK_GOOGLE", default=True),
        mock_website_url=mock_url,
        google_delay_min_s=float(os.getenv("GOOGLE_DELAY_MIN", "2.0")),
        google_delay_max_s=float(os.getenv("GOOGLE_DELAY_MAX", "6.0")),
        playwright_proxy_server=os.getenv("PLAYWRIGHT_PROXY_SERVER") or None,
        search_provider=(os.getenv("SEARCH_PROVIDER") or "duckduckgo").strip().lower(),
        google_cse_api_key=os.getenv("GOOGLE_CSE_API_KEY") or None,
        google_cse_cx=os.getenv("GOOGLE_CSE_CX") or None,
        search_playwright_fallback=_bool_env("SEARCH_PLAYWRIGHT_FALLBACK", default=False),
        cse_delay_s=float(os.getenv("CSE_DELAY_S", "0.25")),
        ddg_delay_s=float(os.getenv("DDG_DELAY_S", "15.0")),
        ddg_api_retries=int(os.getenv("DDG_API_RETRIES", "1")),
        ddg_use_html_fallback=_bool_env("DDG_USE_HTML_FALLBACK", default=False),
        ddg_ratelimit_cooldown_s=float(os.getenv("DDG_RATELIMIT_COOLDOWN_S", "120")),
        ddg_max_variants=int(os.getenv("DDG_MAX_VARIANTS", "1")),
    )


def _bool_env(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}
