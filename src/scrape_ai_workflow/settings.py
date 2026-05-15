from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    """Runtime configuration from environment."""

    # ScrapeGraph Extract API
    scrapegraph_api_key: str | None
    scrapegraph_extract_url: str
    dry_run_extract: bool

    # URL Discovery
    mock_google: bool
    mock_website_url: str | None
    playwright_proxy_server: str | None


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
        playwright_proxy_server=os.getenv("PLAYWRIGHT_PROXY_SERVER") or None,
    )


def _bool_env(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}
