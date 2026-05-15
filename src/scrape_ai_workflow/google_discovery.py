"""
URL Discovery — Playwright + Google Search (stealth mode).

Uses playwright-stealth to avoid bot detection.
Rotates user agents, adds human-like behavior.
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

# ─── Blocked domains ───
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

# Rotate these real Chrome user agents
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
]

# Rotate Google domains to avoid single-domain fingerprinting
_GOOGLE_DOMAINS = [
    "https://www.google.com",
    "https://www.google.co.in",
    "https://www.google.com",   # weight google.com more
    "https://www.google.com",
]


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
    path = urlparse(url).path.lower()
    if "/search" in path or "/sorry" in path:
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Browser management
# ─────────────────────────────────────────────────────────────────────────────

_BROWSER = None
_PW_INSTANCE = None


def _ensure_browser(settings: Settings):
    """Launch stealth browser once, reuse for all searches."""
    global _BROWSER, _PW_INSTANCE

    if _BROWSER is not None:
        try:
            _BROWSER.contexts  # test alive
            return _BROWSER
        except Exception:
            _BROWSER = None
            _PW_INSTANCE = None

    from playwright.sync_api import sync_playwright

    print("  ⏳ Launching browser (one-time)...", flush=True)
    _PW_INSTANCE = sync_playwright().start()

    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-extensions",
        "--disable-infobars",
        "--disable-web-security",
        "--disable-features=IsolateOrigins,site-per-process",
        "--window-size=1366,768",
    ]
    if settings.playwright_proxy_server:
        _BROWSER = _PW_INSTANCE.chromium.launch(
            headless=True,
            args=launch_args,
            proxy={"server": settings.playwright_proxy_server},
        )
    else:
        _BROWSER = _PW_INSTANCE.chromium.launch(
            headless=True,
            args=launch_args,
        )
    print("  ✅ Browser ready.", flush=True)
    return _BROWSER


def _new_stealth_page(browser, ua: str):
    """Create a new page with stealth settings."""
    context = browser.new_context(
        user_agent=ua,
        viewport={"width": random.randint(1280, 1440), "height": random.randint(700, 800)},
        locale="en-US",
        timezone_id="America/New_York",
        java_script_enabled=True,
        has_touch=False,
        is_mobile=False,
        color_scheme="light",
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "sec-ch-ua": '"Chromium";v="126", "Google Chrome";v="126"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-Mode": "navigate",
            "Upgrade-Insecure-Requests": "1",
        },
    )

    # Apply stealth JS patches if playwright-stealth is installed
    try:
        from playwright_stealth import stealth_sync
        page = context.new_page()
        stealth_sync(page)
    except ImportError:
        page = context.new_page()

    # Block heavy resources for speed
    context.route(
        "**/*.{png,jpg,jpeg,gif,svg,ico,woff,woff2,ttf,mp4,webm,mp3}",
        lambda route: route.abort(),
    )

    # Remove webdriver property via JS
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        window.chrome = { runtime: {} };
    """)

    return page, context


def _human_behavior(page) -> None:
    """Simulate human-like mouse + scroll behavior."""
    try:
        # Random scroll
        page.evaluate(f"window.scrollBy(0, {random.randint(100, 400)})")
        time.sleep(random.uniform(0.3, 0.8))
        # Move mouse to random position
        page.mouse.move(random.randint(200, 900), random.randint(100, 500))
        time.sleep(random.uniform(0.2, 0.5))
    except Exception:
        pass


def _dismiss_consent(page) -> None:
    """Dismiss Google cookie/consent popup."""
    try:
        selectors = [
            "button#L2AGLb",
            "button[aria-label*='Accept all']",
            "button[aria-label*='Accept']",
            "form[action*='consent'] button",
        ]
        for sel in selectors:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                time.sleep(random.uniform(1.0, 2.0))
                return
    except Exception:
        pass


def _is_captcha(html: str) -> bool:
    lower = html.lower()
    return "/sorry/" in lower or "captcha" in lower or "unusual traffic" in lower or "i'm not a robot" in lower


def _extract_results(html: str) -> list[tuple[str, str, str]]:
    """Parse Google SERP and extract organic results."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    results: list[tuple[str, str, str]] = []
    seen_hosts: set[str] = set()

    # Strategy 1: Standard organic result containers
    for container in soup.select("div.g, div.tF2Cxc, div.Gx5Zad, div[data-hveid]"):
        a_tag = container.select_one("a[href^='http']")
        if not a_tag:
            continue
        href = a_tag.get("href", "").strip()
        if not href.startswith("http") or _is_blocked(href):
            continue
        host = _host(href)
        if host in seen_hosts:
            continue
        seen_hosts.add(host)
        h3 = container.select_one("h3")
        title = h3.get_text(" ", strip=True) if h3 else a_tag.get_text(" ", strip=True)
        snippet = ""
        for sel in [".VwiC3b", ".lEBKkf", ".IsZvec", "span.st"]:
            el = container.select_one(sel)
            if el:
                snippet = el.get_text(" ", strip=True)
                break
        results.append((href, title[:150], snippet[:200]))

    # Strategy 2: Any <a> with h3 — catches newer Google layouts
    if len(results) < 3:
        for a_tag in soup.select("a[href^='http'] h3"):
            a = a_tag.find_parent("a")
            if not a:
                continue
            href = a.get("href", "").strip()
            if _is_blocked(href):
                continue
            host = _host(href)
            if host in seen_hosts:
                continue
            seen_hosts.add(host)
            results.append((href, a_tag.get_text(" ", strip=True), ""))

    return results[:20]


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def discover_official_website(company_name: str, settings: Settings) -> GooglePick:
    """
    Discover official website URL using stealth Playwright + Google.
    - Rotates user agents + Google domains
    - Stealth mode (playwright-stealth if installed)
    - Human-like behavior (scroll, mouse)
    - CAPTCHA detection + long wait
    - 3 query variants
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
        from bs4 import BeautifulSoup  # noqa — verify installed
    except ImportError:
        return GooglePick(None, "missing_dep", "pip install beautifulsoup4")

    try:
        browser = _ensure_browser(settings)
    except Exception as e:
        return GooglePick(None, "browser_error", str(e)[:200])

    queries = [
        build_search_query(name, variant=0),
        build_search_query(name, variant=1),
        build_search_query(name, variant=2),
    ]

    for attempt, query in enumerate(queries):
        if attempt == 0:
            print(f"  🌐 Google: '{query}'", flush=True)
        else:
            print(f"  🔄 Retry [{attempt+1}]: '{query}'", flush=True)

        ua = random.choice(_USER_AGENTS)
        domain = random.choice(_GOOGLE_DOMAINS)
        encoded = query.replace(" ", "+")
        url = f"{domain}/search?q={encoded}&hl=en&num=20&gl=us"

        page = None
        context = None
        try:
            page, context = _new_stealth_page(browser, ua)
            page.goto(url, wait_until="domcontentloaded", timeout=25000)

            # Dismiss consent
            _dismiss_consent(page)

            # Human-like wait + behavior
            time.sleep(random.uniform(2.5, 5.0))
            _human_behavior(page)

            html = page.content()

            if _is_captcha(html):
                print(f"  🚫 CAPTCHA detected! ({attempt+1}/3)", flush=True)
                if attempt >= 1:
                    # 2nd+ CAPTCHA — wait long then stop trying
                    wait = random.uniform(240, 360)
                    print(f"  ⛔ IP temporarily blocked. Waiting {wait/60:.1f} min...", flush=True)
                    time.sleep(wait)
                    return GooglePick(None, "captcha", "IP blocked — retrying next session")
                # 1st CAPTCHA — wait shorter and try next variant
                time.sleep(random.uniform(60, 90))
                continue

            results = _extract_results(html)
            print(f"  📋 Results: {len(results)} links found", flush=True)

            if results:
                best, score, detail = pick_best_url(name, results)
                if best:
                    print(f"  ✅ URL: {best}  (score={score:.1f})", flush=True)
                    return GooglePick(best, "picked", f"{detail}; score={score:.1f}")
                # Low confidence — return first result anyway
                first_url = results[0][0]
                print(f"  ⚠️  Low confidence, using first: {first_url}", flush=True)
                return GooglePick(first_url, "low_confidence", f"first_result; score={score:.1f}")

        except Exception as e:
            print(f"  ⚠️  Error: {str(e)[:100]}", flush=True)
            time.sleep(5)

        finally:
            try:
                if page:
                    page.close()
                if context:
                    context.close()
            except Exception:
                pass
            # Polite delay between queries
            time.sleep(random.uniform(4, 8))

    print(f"  ❌ All queries failed for: '{name}'", flush=True)
    return GooglePick(None, "no_results", f"all queries failed")


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
