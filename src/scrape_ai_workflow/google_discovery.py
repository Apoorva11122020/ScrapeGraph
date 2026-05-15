from __future__ import annotations

import logging
import random
import re
import time
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

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

GOOGLE_CSE_ENDPOINT = "https://www.googleapis.com/customsearch/v1"

# ─── Shared browser instance for Playwright (reuse across calls) ───
_BROWSER = None
_BROWSER_CONTEXT = None


@dataclass(frozen=True)
class GooglePick:
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
# PLAYWRIGHT + BING SEARCH (primary method — reliable for 90+ companies)
# ─────────────────────────────────────────────────────────────────────────────

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]


def _get_browser_context(settings: Settings):
    """Get or create a persistent browser context (reuses across all searches in a run)."""
    global _BROWSER, _BROWSER_CONTEXT

    if _BROWSER_CONTEXT is not None:
        try:
            _BROWSER_CONTEXT.pages  # test if still alive
            return _BROWSER_CONTEXT
        except Exception:
            _BROWSER = None
            _BROWSER_CONTEXT = None

    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    launch_args = {
        "headless": True,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ],
    }
    if settings.playwright_proxy_server:
        launch_args["proxy"] = {"server": settings.playwright_proxy_server}

    _BROWSER = pw.chromium.launch(**launch_args)
    _BROWSER_CONTEXT = _BROWSER.new_context(
        user_agent=random.choice(_USER_AGENTS),
        viewport={"width": 1366, "height": 768},
        locale="en-US",
    )
    # Block images/media/fonts to speed things up
    _BROWSER_CONTEXT.route(
        "**/*.{png,jpg,jpeg,gif,svg,ico,woff,woff2,ttf,mp4,webm,mp3}",
        lambda route: route.abort(),
    )
    return _BROWSER_CONTEXT


def _extract_bing_results(page) -> list[tuple[str, str, str]]:
    """Extract organic search results from Bing SERP page."""
    results: list[tuple[str, str, str]] = []

    try:
        page.wait_for_selector("#b_results li.b_algo", timeout=15000)
    except Exception:
        pass

    html = page.content()
    soup = BeautifulSoup(html, "html.parser")

    for item in soup.select("#b_results li.b_algo"):
        a_tag = item.select_one("h2 a[href]")
        if not a_tag:
            continue
        href = a_tag.get("href", "").strip()
        if not href.startswith("http"):
            continue
        title = a_tag.get_text(" ", strip=True)
        snippet_el = item.select_one(".b_caption p, .b_algoSlug")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        if not _is_blocked(href):
            results.append((href, title, snippet))

    return results


def _discover_playwright_bing(company_name: str, settings: Settings) -> GooglePick:
    """
    Use Playwright to search Bing.com — reliable, no rate limits for 90 companies.
    Bing is much less aggressive with CAPTCHAs than Google.
    ~8-12s per company = ~15 min for 90 companies.
    """
    query = build_search_query(company_name, variant=0)
    delay = settings.playwright_search_delay_s

    try:
        context = _get_browser_context(settings)
        page = context.new_page()

        try:
            # Navigate directly to Bing search URL
            search_url = "https://www.bing.com/search?q=" + query.replace(" ", "+") + "&setlang=en"
            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

            # Small random wait to appear human
            time.sleep(random.uniform(1.5, 3.0))

            results = _extract_bing_results(page)

            if not results:
                # Try alternate query variant
                query2 = build_search_query(company_name, variant=2)
                search_url2 = "https://www.bing.com/search?q=" + query2.replace(" ", "+") + "&setlang=en"
                page.goto(search_url2, wait_until="domcontentloaded", timeout=30000)
                time.sleep(random.uniform(1.5, 2.5))
                results = _extract_bing_results(page)

            if not results:
                # Last resort: variant 1
                query3 = build_search_query(company_name, variant=1)
                search_url3 = "https://www.bing.com/search?q=" + query3.replace(" ", "+") + "&setlang=en"
                page.goto(search_url3, wait_until="domcontentloaded", timeout=30000)
                time.sleep(random.uniform(1.5, 2.5))
                results = _extract_bing_results(page)

            if not results:
                return GooglePick(None, "bing_no_results", f"query={query}")

            best, score, detail = pick_best_url(company_name, results)
            if not best:
                return GooglePick(None, "low_confidence", detail)
            return GooglePick(best, "picked_bing", f"{detail}; score={score:.1f}")

        finally:
            page.close()
            # Polite delay between searches
            time.sleep(delay + random.uniform(0, 2.0))

    except Exception as e:
        log.error("Playwright Bing error for %r: %s", company_name, e)
        return GooglePick(None, "playwright_error", str(e)[:200])


# ─────────────────────────────────────────────────────────────────────────────
# GOOGLE CSE (paid path for 20k scale)
# ─────────────────────────────────────────────────────────────────────────────

def _discover_via_google_cse(company_name: str, query: str, settings: Settings) -> GooglePick:
    key = (settings.google_cse_api_key or "").strip()
    cx = (settings.google_cse_cx or "").strip()
    if not key or not cx:
        return GooglePick(None, "cse_not_configured", "set GOOGLE_CSE_API_KEY and GOOGLE_CSE_CX")

    time.sleep(max(0.0, settings.cse_delay_s))
    params = {"key": key, "cx": cx, "q": query, "num": 10}

    for attempt in range(3):
        try:
            with httpx.Client(timeout=45.0) as client:
                r = client.get(GOOGLE_CSE_ENDPOINT, params=params)
            if r.status_code in (429, 500, 503) and attempt < 2:
                time.sleep(2.0 * (attempt + 1))
                continue
            if r.status_code != 200:
                return GooglePick(None, "cse_error", f"http_{r.status_code}")
            items = r.json().get("items") or []
            tuples = []
            for it in items:
                link = it.get("link")
                if isinstance(link, str) and link.startswith("http") and not _is_blocked(link):
                    tuples.append((link, str(it.get("title") or ""), str(it.get("snippet") or "")))
            if not tuples:
                return GooglePick(None, "cse_no_results", "no links")
            best, score, detail = pick_best_url(company_name, tuples)
            if not best:
                return GooglePick(None, "low_confidence", detail)
            return GooglePick(best, "picked_cse", f"{detail}; score={score:.1f}")
        except httpx.HTTPError as e:
            if attempt < 2:
                time.sleep(2.0)
                continue
            return GooglePick(None, "cse_error", str(e))
    return GooglePick(None, "cse_error", "retries exhausted")


# ─────────────────────────────────────────────────────────────────────────────
# DDG FALLBACK (kept as option but NOT recommended — rate limits)
# ─────────────────────────────────────────────────────────────────────────────

def _ddg_api_search(company_name: str, query: str) -> GooglePick:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return GooglePick(None, "ddg_api_missing", "pip install duckduckgo-search")
    try:
        with DDGS() as ddgs:
            hits = list(ddgs.text(query, max_results=12, backend="auto"))
    except Exception as e:
        return GooglePick(None, "ddg_api_error", str(e)[:200])
    if not hits:
        return GooglePick(None, "ddg_no_results", "empty result set")
    tuples: list[tuple[str, str, str]] = []
    for h in hits:
        url = (h.get("href") or "").strip()
        if url.startswith("http") and not _is_blocked(url):
            tuples.append((url, str(h.get("title") or ""), str(h.get("body") or "")))
    if not tuples:
        return GooglePick(None, "ddg_no_usable", "all filtered")
    best, score, detail = pick_best_url(company_name, tuples)
    if not best:
        return GooglePick(None, "low_confidence", detail)
    return GooglePick(best, "picked_ddg", f"{detail}; score={score:.1f}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def discover_official_website(company_name: str, settings: Settings) -> GooglePick:
    """
    Discover the official website URL for a company name.
    Default provider: playwright_bing (Playwright + Bing search).
    """
    name = " ".join(str(company_name).split()).strip()
    if not name:
        return GooglePick(None, "invalid_company", "empty name")

    if settings.mock_google:
        u = (settings.mock_website_url or "").strip()
        if u:
            return GooglePick(u, "mock_google", "MOCK_GOOGLE=true")
        return GooglePick(None, "mock_google_no_url", "MOCK_WEBSITE_URL empty")

    provider = (settings.search_provider or "playwright_bing").strip().lower()

    # Aliases for backward compat
    if provider in ("playwright", "google", "bing"):
        provider = "playwright_bing"

    if provider == "cse":
        return _discover_via_google_cse(name, build_search_query(name), settings)

    if provider in ("duckduckgo", "ddg"):
        time.sleep(settings.ddg_delay_s)
        return _ddg_api_search(name, build_search_query(name))

    if provider == "auto":
        cse_ready = bool((settings.google_cse_api_key or "").strip() and (settings.google_cse_cx or "").strip())
        if cse_ready:
            cse = _discover_via_google_cse(name, build_search_query(name), settings)
            if cse.url:
                return cse
        # Fallback to Playwright Bing
        return _discover_playwright_bing(name, settings)

    # Default: playwright_bing
    return _discover_playwright_bing(name, settings)


def close_browser():
    """Call at end of pipeline to cleanly close the shared browser."""
    global _BROWSER, _BROWSER_CONTEXT
    try:
        if _BROWSER_CONTEXT:
            _BROWSER_CONTEXT.close()
        if _BROWSER:
            _BROWSER.close()
    except Exception:
        pass
    _BROWSER = None
    _BROWSER_CONTEXT = None
