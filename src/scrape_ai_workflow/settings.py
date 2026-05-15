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
    google_search_delay_s: float
    use_playwright_fallback: bool
    playwright_proxy_server: str | None
    search_provider: str
    google_cse_api_key: str | None
    google_cse_cx: str | None
    cse_delay_s: float
    ddg_delay_s: float


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
        google_search_delay_s=float(os.getenv("GOOGLE_SEARCH_DELAY_S", "10.0")),
        use_playwright_fallback=_bool_env("USE_PLAYWRIGHT_FALLBACK", default=True),
        playwright_proxy_server=os.getenv("PLAYWRIGHT_PROXY_SERVER") or None,
        search_provider=(os.getenv("SEARCH_PROVIDER") or "google").strip().lower(),
        google_cse_api_key=os.getenv("GOOGLE_CSE_API_KEY") or None,
        google_cse_cx=os.getenv("GOOGLE_CSE_CX") or None,
        cse_delay_s=float(os.getenv("CSE_DELAY_S", "0.25")),
        ddg_delay_s=float(os.getenv("DDG_DELAY_S", "15.0")),
    )


def _bool_env(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}
