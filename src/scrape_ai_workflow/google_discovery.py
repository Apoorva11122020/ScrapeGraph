"""
URL Discovery — Playwright + Google Search.

Single method: headless Chromium browser searches Google.
Handles CAPTCHAs, retries, consent pages, multiple query variants.
Reuses browser across all companies for speed.
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

# ─── Blocked domains (directories, social media, not company sites) ───
_BLOCKED_PATTERNS = (
    "google.", "gstatic.", "googleapis.",
    "youtube.", "youtu.be",
    "facebook.", "fb.com", "fb.me",
    "instagram.", "linkedin.", "twitter.", "x.com",
    "maps.google", "play.google",
    "indiamart.com", "justdial.com", "tradeindia.com",
    "zaubacorp.com", "tofler.in", "crunchbase.com",
    "wikipedia.org", "wikimedia.org",
    "reddit.", "pinterest.", "quora.com",
    "duckduckgo.com", "bing.com", "yahoo.com",
    "springer.com", "microsoft.com", "msn.com",
    "amazon.com", "flipkart.com", "myntra.com",
    "glassdoor.", "naukri.com", "indeed.com",
    "accounts.google", "support.google",
    "translate.google", "scholar.google",
    "news.google", "books.google",
    "webcache.googleusercontent",
)


@dataclass(frozen=True)
class GooglePick:
    """Result of URL discovery."""
    url: str | None
    status: str
    detail: str


def _host(url: str) -> str:
    try:
        return urlparse(url).netloc.casefold()
    except Exception:
        return ""


def _is_blocked(url: str) -> bool:
    host = _host(url)
    if not host:
        return True
    for pattern in _BLOCKED_PATTERNS:
        if pattern in host:
            return True
    # Block URLs that are clearly not homepages (too deep paths like /search?q=)
    path = urlparse(url).path.lower()
    if "/search" in path or "/sorry" in path:
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# PLAYWRIGHT + GOOGLE (single reliable method)
# ─────────────────────────────────────────────────────────────────────────────

_BROWSER = None
_PW_INSTANCE = None
_CONTEXT = None

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
]


def _ensure_browser(settings: Settings):
    """Launch browser once, reuse for all searches."""
    global _BROWSER, _PW_INSTANCE, _CONTEXT

    if _CONTEXT is not None:
        try:
            _CONTEXT.pages  # test alive
            return _CONTEXT
        except Exception:
            _BROWSER = None
            _PW_INSTANCE = None
            _CONTEXT = None

    from playwright.sync_api import sync_playwright

    print("  ⏳ Launching browser (one-time)...", flush=True)
    _PW_INSTANCE = sync_playwright().start()

    launch_args = {
        "headless": True,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-extensions",
            "--disable-infobars",
        ],
    }
    if settings.playwright_proxy_server:
        launch_args["proxy"] = {"server": settings.playwright_proxy_server}

    _BROWSER = _PW_INSTANCE.chromium.launch(**launch_args)
    _CONTEXT = _BROWSER.new_context(
        user_agent=random.choice(_USER_AGENTS),
        viewport={"width": 1366, "height": 768},
        locale="en-US",
        timezone_id="America/New_York",
        java_script_enabled=True,
    )
    # Block heavy resources for speed
    _CONTEXT.route("**/*.{png,jpg,jpeg,gif,svg,ico,woff,woff2,ttf,mp4,webm,mp3,css}", lambda route: route.abort())
    print("  ✅ Browser ready.", flush=True)
    return _CONTEXT


def _dismiss_consent(page) -> None:
    """Dismiss Google cookie consent if shown."""
    try:
        # Multiple selectors for different Google consent versions
        selectors = [
            "button#L2AGLb",           # "I agree" button
            "button[aria-label*='Accept']",
            "button[aria-label*='accept']",
            "form[action*='consent'] button",
            "div[role='dialog'] button:first-of-type",
        ]
        for sel in selectors:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                time.sleep(1)
                return
    except Exception:
        pass


def _extract_google_results(html: str) -> list[tuple[str, str, str]]:
    """Parse Google SERP HTML and extract organic results."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    results: list[tuple[str, str, str]] = []
    seen_hosts: set[str] = set()

    # Strategy 1: Standard Google organic results (div.g or similar)
    for container in soup.select("div.g, div[data-hveid] div.tF2Cxc, div.Gx5Zad"):
        a_tag = container.select_one("a[href^='http']")
        if not a_tag:
            continue
        href = a_tag.get("href", "").strip()
        if not href.startswith("http") or _is_blocked(href):
            continue

        # Skip duplicate domains
        host = _host(href)
        if host in seen_hosts:
            continue
        seen_hosts.add(host)

        title = ""
        h3 = container.select_one("h3")
        if h3:
            title = h3.get_text(" ", strip=True)
        if not title:
            title = a_tag.get_text(" ", strip=True)

        snippet = ""
        for sel in [".VwiC3b", ".lEBKkf", "span.st", ".IsZvec"]:
            snip_el = container.select_one(sel)
            if snip_el:
                snippet = snip_el.get_text(" ", strip=True)
                break

        results.append((href, title[:150], snippet[:200]))

    # Strategy 2: Broader — any <a> with h3 inside (catches newer layouts)
    if len(results) < 3:
        for a_tag in soup.select("a[href^='http']"):
            href = a_tag.get("href", "").strip()
            if _is_blocked(href):
                continue
            host = _host(href)
            if host in seen_hosts:
                continue
            # Must have a heading or meaningful text
            h3 = a_tag.select_one("h3")
            title = h3.get_text(" ", strip=True) if h3 else a_tag.get_text(" ", strip=True)[:80]
            if len(title) < 3:
                continue
            seen_hosts.add(host)
            results.append((href, title, ""))

    return results[:20]  # Max 20 results to rank


def _search_google(page, query: str) -> str:
    """Navigate to Google search and return page HTML."""
    encoded_query = query.replace(" ", "+")
    url = f"https://www.google.com/search?q={encoded_query}&hl=en&num=15&gl=us"
    page.goto(url, wait_until="domcontentloaded", timeout=25000)

    # Dismiss consent/cookie popup if shown
    _dismiss_consent(page)

    # Human-like wait
    time.sleep(random.uniform(2.0, 4.0))

    # Scroll down slightly (human behavior)
    page.evaluate("window.scrollBy(0, 300)")
    time.sleep(random.uniform(0.5, 1.5))

    return page.content()


def _is_captcha(html: str) -> bool:
    """Check if Google is showing CAPTCHA/sorry page."""
    lower = html.lower()
    return "/sorry/" in lower or "captcha" in lower or "unusual traffic" in lower


def discover_official_website(company_name: str, settings: Settings) -> GooglePick:
    """
    Discover official website URL using Playwright + Google.

    Flow:
    1. Search Google with company name
    2. Parse organic results
    3. Rank using url_ranking.py
    4. If no results or CAPTCHA: retry with variant queries
    5. If all fail: return failure with details
    """
    name = " ".join(str(company_name).split()).strip()
    if not name:
        return GooglePick(None, "invalid_company", "empty name")

    if settings.mock_google:
        u = (settings.mock_website_url or "").strip()
        if u:
            return GooglePick(u, "mock_google", "MOCK_GOOGLE=true")
        return GooglePick(None, "mock_google_no_url", "MOCK_WEBSITE_URL empty")

    try:
        from bs4 import BeautifulSoup  # noqa: F401 — verify import early
    except ImportError:
        return GooglePick(None, "missing_dep", "pip install beautifulsoup4")

    # Ensure browser is running
    try:
        context = _ensure_browser(settings)
    except Exception as e:
        return GooglePick(None, "browser_error", f"Failed to launch: {e}")

    # Build query variants
    queries = [
        build_search_query(name, variant=0),  # "Company Name"
        build_search_query(name, variant=1),  # "Company Name company"
        build_search_query(name, variant=2),  # "Company Name official website"
    ]

    captcha_count = 0
    last_detail = ""

    for attempt, query in enumerate(queries):
        if attempt == 0:
            print(f"  🌐 Google: '{query}'", flush=True)
        else:
            print(f"  🔄 Retry [{attempt+1}]: '{query}'", flush=True)

        page = context.new_page()
        try:
            html = _search_google(page, query)

            # Check for CAPTCHA
            if _is_captcha(html):
                captcha_count += 1
                print(f"  🚫 CAPTCHA detected! ({captcha_count}/3)", flush=True)
                if captcha_count >= 2:
                    # Don't keep trying — Google is blocking this IP
                    print(f"  ⛔ IP blocked by Google. Waiting 3 min before next company...", flush=True)
                    time.sleep(180)
                    return GooglePick(None, "captcha", "Google blocking IP — try later or use proxy")
                # Wait and try different query
                time.sleep(random.uniform(30, 60))
                continue

            # Parse results
            results = _extract_google_results(html)
            print(f"  📋 Results: {len(results)} links found", flush=True)

            if results:
                best, score, detail = pick_best_url(name, results)
                if best:
                    print(f"  ✅ URL: {best}  (score={score:.1f})", flush=True)
                    return GooglePick(best, "picked", f"{detail}; score={score:.1f}")
                else:
                    # Score too low — use first result anyway (better than nothing)
                    first_url = results[0][0]
                    print(f"  ⚠️  Low confidence, using first: {first_url}", flush=True)
                    return GooglePick(first_url, "low_confidence", f"first_result; {detail}")

            last_detail = f"query='{query}' returned 0 results"

        except Exception as e:
            last_detail = str(e)[:200]
            print(f"  ⚠️  Error: {last_detail}", flush=True)
            time.sleep(5)

        finally:
            page.close()
            # Polite delay between searches
            time.sleep(random.uniform(3, 6))

    print(f"  ❌ All queries failed for: '{name}'", flush=True)
    return GooglePick(None, "no_results", last_detail)


def close_browser():
    """Cleanly close Playwright browser at end of pipeline."""
    global _BROWSER, _PW_INSTANCE, _CONTEXT
    try:
        if _CONTEXT:
            _CONTEXT.close()
        if _BROWSER:
            _BROWSER.close()
        if _PW_INSTANCE:
            _PW_INSTANCE.stop()
    except Exception:
        pass
    _BROWSER = None
    _PW_INSTANCE = None
    _CONTEXT = None
    print("🔒 Browser closed.", flush=True)
