"""
URL Discovery module — finds official website for a company name.

Primary method: googlesearch-python (free, no API key needed)
Fallback: Playwright + Google (headless browser)
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse

from .search_query import build_search_query
from .settings import Settings
from .url_ranking import pick_best_url

log = logging.getLogger(__name__)

_DEFAULT_BLOCKED = (
    "google.",
    "gstatic.",
    "youtube.",
    "youtu.be",
    "facebook.",
    "fb.com",
    "instagram.",
    "linkedin.",
    "twitter.",
    "x.com",
    "maps.google",
    "play.google",
    "indiamart.com",
    "justdial.com",
    "zaubacorp.com",
    "tofler.in",
    "crunchbase.com",
    "wikipedia.org",
    "reddit.",
    "pinterest.",
    "duckduckgo.com",
    "bing.com",
    "springer.com",
    "microsoft.com",
    "msn.com",
)


@dataclass(frozen=True)
class GooglePick:
    """Result of URL discovery — same interface used by pipeline.py"""
    url: str | None
    status: str
    detail: str


def _host(url: str) -> str:
    try:
        return urlparse(url).netloc.casefold()
    except Exception:
        return ""


def _is_blocked(url: str, extra_blocked: Iterable[str] | None = None) -> bool:
    host = _host(url)
    if not host:
        return True
    for b in _DEFAULT_BLOCKED:
        if b in host:
            return True
    if extra_blocked:
        for b in extra_blocked:
            if b.casefold() in host:
                return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# PRIMARY: googlesearch-python (free, no API key)
# ─────────────────────────────────────────────────────────────────────────────

def _discover_google_search(company_name: str, settings: Settings) -> GooglePick:
    """
    Use googlesearch-python to search Google.
    Free, no API key needed. Works great for 90 companies with delays.
    """
    try:
        from googlesearch import search as gsearch
    except ImportError:
        print("  ❌ googlesearch-python not installed! Run: pip install googlesearch-python", flush=True)
        return GooglePick(None, "import_error", "pip install googlesearch-python")

    queries = [
        build_search_query(company_name, variant=0),
        build_search_query(company_name, variant=1),
        build_search_query(company_name, variant=2),
    ]

    delay = settings.google_search_delay_s

    for attempt, query in enumerate(queries):
        if attempt == 0:
            print(f"  🌐 Google: '{query}'", flush=True)
        else:
            print(f"  🔄 Retry [{attempt+1}]: '{query}'", flush=True)

        try:
            # googlesearch-python returns list of URLs
            raw_results = list(gsearch(
                query,
                num_results=10,
                lang="en",
                sleep_interval=5,
            ))
            # Filter blocked
            good_results: list[tuple[str, str, str]] = []
            for url in raw_results:
                if isinstance(url, str) and url.startswith("http") and not _is_blocked(url):
                    good_results.append((url, "", ""))

            print(f"  📋 Results: {len(raw_results)} raw → {len(good_results)} usable", flush=True)

            if good_results:
                best, score, detail = pick_best_url(company_name, good_results)
                if best:
                    print(f"  ✅ URL: {best}  (score={score:.1f})", flush=True)
                    return GooglePick(best, "picked_google", f"{detail}; score={score:.1f}")
                else:
                    # Score too low but we have results — take first one anyway for review
                    first_url = good_results[0][0]
                    print(f"  ⚠️  Low confidence, using first: {first_url}", flush=True)
                    return GooglePick(first_url, "low_confidence_picked", f"first_result; {detail}")

        except Exception as e:
            err_str = str(e).lower()
            print(f"  ⚠️  Error: {e}", flush=True)

            if "429" in err_str or "too many" in err_str or "http error 429" in err_str:
                wait = random.uniform(90, 150)
                print(f"  ⏸️  Rate limited! Waiting {wait:.0f}s...", flush=True)
                time.sleep(wait)
                # Don't retry more queries — go straight to fallback
                break
            else:
                time.sleep(5)
                continue

        # Polite delay between variant queries
        time.sleep(delay + random.uniform(1, 3))

    return GooglePick(None, "google_no_results", f"all queries failed for: {company_name}")


# ─────────────────────────────────────────────────────────────────────────────
# FALLBACK: Playwright + Google (headless browser)
# ─────────────────────────────────────────────────────────────────────────────

_BROWSER = None
_PW_INSTANCE = None


def _discover_playwright_google(company_name: str, settings: Settings) -> GooglePick:
    """Fallback: use Playwright headless browser to search Google."""
    global _BROWSER, _PW_INSTANCE

    try:
        from playwright.sync_api import sync_playwright
        from bs4 import BeautifulSoup
    except ImportError:
        return GooglePick(None, "playwright_not_installed", "pip install playwright beautifulsoup4")

    print(f"  🌐 Playwright Google fallback...", flush=True)

    try:
        if _PW_INSTANCE is None or _BROWSER is None:
            print("  ⏳ Launching browser...", flush=True)
            _PW_INSTANCE = sync_playwright().start()
            _BROWSER = _PW_INSTANCE.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            print("  ✅ Browser ready.", flush=True)

        context = _BROWSER.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="en-US",
        )
        page = context.new_page()

        query = build_search_query(company_name, variant=0)
        search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}&hl=en&num=10"
        page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(random.uniform(2, 4))

        html = page.content()
        page.close()
        context.close()

        soup = BeautifulSoup(html, "html.parser")

        # Extract links from Google results
        good_results: list[tuple[str, str, str]] = []
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if href.startswith("http") and not _is_blocked(href):
                title = a.get_text(" ", strip=True)[:100]
                if len(title) > 2:
                    good_results.append((href, title, ""))

        # Deduplicate
        seen = set()
        deduped = []
        for r in good_results:
            if r[0] not in seen:
                seen.add(r[0])
                deduped.append(r)
        good_results = deduped[:15]

        print(f"  📋 Playwright found: {len(good_results)} links", flush=True)

        if good_results:
            best, score, detail = pick_best_url(company_name, good_results)
            if best:
                print(f"  ✅ URL: {best}  (score={score:.1f})", flush=True)
                return GooglePick(best, "picked_playwright", f"{detail}; score={score:.1f}")
            first_url = good_results[0][0]
            print(f"  ⚠️  Low confidence, using first: {first_url}", flush=True)
            return GooglePick(first_url, "low_confidence_playwright", detail)

        # Check for CAPTCHA
        if "sorry" in html.lower() or "captcha" in html.lower():
            print("  🚫 Google CAPTCHA detected!", flush=True)
            return GooglePick(None, "captcha", "Google showed CAPTCHA")

        return GooglePick(None, "playwright_no_results", "no links found")

    except Exception as e:
        print(f"  ❌ Playwright error: {e}", flush=True)
        return GooglePick(None, "playwright_error", str(e)[:200])


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def discover_official_website(company_name: str, settings: Settings) -> GooglePick:
    """
    Discover official website URL.
    1. googlesearch-python (primary — free, no key)
    2. Playwright + Google (fallback if rate limited)
    """
    name = " ".join(str(company_name).split()).strip()
    if not name:
        return GooglePick(None, "invalid_company", "empty name")

    if settings.mock_google:
        u = (settings.mock_website_url or "").strip()
        if u:
            return GooglePick(u, "mock_google", "MOCK_GOOGLE=true")
        return GooglePick(None, "mock_google_no_url", "MOCK_WEBSITE_URL empty")

    # Primary: googlesearch-python
    result = _discover_google_search(name, settings)
    if result.url:
        return result

    # Fallback: Playwright
    if settings.use_playwright_fallback:
        print(f"  🔄 Primary failed, trying Playwright fallback...", flush=True)
        pw_result = _discover_playwright_google(name, settings)
        if pw_result.url:
            return pw_result

    return result  # Return the failed result with status/detail


def close_browser():
    """Cleanly close Playwright browser at end of pipeline."""
    global _BROWSER, _PW_INSTANCE
    try:
        if _BROWSER:
            _BROWSER.close()
        if _PW_INSTANCE:
            _PW_INSTANCE.stop()
    except Exception:
        pass
    _BROWSER = None
    _PW_INSTANCE = None
    print("🔒 Browser closed.", flush=True)
