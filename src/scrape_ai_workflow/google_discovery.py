"""
URL Discovery — Multi-Engine Fallback (Google → Bing → DuckDuckGo → Skip).

Cascade logic:
  ① Playwright + Google (stealth)
  ② Playwright + Bing (if Google CAPTCHA / blocked)
  ③ DuckDuckGo HTML (no API key needed)
  ④ Skip company (don't block pipeline)

Once Google is blocked (CAPTCHA), all subsequent companies auto-switch to Bing first.
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import quote_plus, urlparse

from .search_query import build_search_query
from .settings import Settings
from .url_ranking import pick_best_url

log = logging.getLogger(__name__)

# ─── Track engine state across companies ───
_GOOGLE_BLOCKED = False  # Flips True when CAPTCHA detected; skip Google for rest of run

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
    "duckduckgo.com", "yahoo.com",
    "springer.com", "microsoft.com", "msn.com",
    "amazon.com", "flipkart.com", "myntra.com",
    "glassdoor.", "naukri.com", "indeed.com",
    "accounts.google", "support.google",
    "translate.google", "scholar.google",
    "news.google", "books.google",
    "webcache.googleusercontent",
)

# Real Chrome user agents
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
]

_GOOGLE_DOMAINS = [
    "https://www.google.com",
    "https://www.google.co.in",
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
# Browser management (shared across engines)
# ─────────────────────────────────────────────────────────────────────────────

_BROWSER = None
_PW_INSTANCE = None


def _ensure_browser(settings: Settings):
    """Launch stealth browser once, reuse for all searches."""
    global _BROWSER, _PW_INSTANCE

    if _BROWSER is not None:
        try:
            _BROWSER.contexts
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
        _BROWSER = _PW_INSTANCE.chromium.launch(headless=True, args=launch_args)
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
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "sec-ch-ua": '"Chromium";v="126", "Google Chrome";v="126"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-Mode": "navigate",
            "Upgrade-Insecure-Requests": "1",
        },
    )

    try:
        from playwright_stealth import stealth_sync
        page = context.new_page()
        stealth_sync(page)
    except ImportError:
        page = context.new_page()

    # Block heavy resources
    context.route(
        "**/*.{png,jpg,jpeg,gif,svg,ico,woff,woff2,ttf,mp4,webm,mp3}",
        lambda route: route.abort(),
    )

    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        window.chrome = { runtime: {} };
    """)

    return page, context


def _human_behavior(page) -> None:
    try:
        page.evaluate(f"window.scrollBy(0, {random.randint(100, 400)})")
        time.sleep(random.uniform(0.3, 0.8))
        page.mouse.move(random.randint(200, 900), random.randint(100, 500))
        time.sleep(random.uniform(0.2, 0.5))
    except Exception:
        pass


def _is_captcha(html: str) -> bool:
    lower = html.lower()
    return any(x in lower for x in ["/sorry/", "captcha", "unusual traffic", "i'm not a robot", "are you a robot"])


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 1: Google
# ─────────────────────────────────────────────────────────────────────────────

def _search_google(query: str, browser, settings: Settings) -> list[tuple[str, str, str]] | None:
    """Search Google. Returns list of (url, title, snippet) or None if CAPTCHA/blocked."""
    global _GOOGLE_BLOCKED

    if _GOOGLE_BLOCKED:
        return None

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
        try:
            for sel in ["button#L2AGLb", "button[aria-label*='Accept all']", "button[aria-label*='Accept']"]:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    time.sleep(random.uniform(1.0, 2.0))
                    break
        except Exception:
            pass

        time.sleep(random.uniform(2.5, 5.0))
        _human_behavior(page)
        html = page.content()

        if _is_captcha(html):
            print(f"  🚫 Google CAPTCHA! Switching to Bing for remaining companies.", flush=True)
            _GOOGLE_BLOCKED = True
            return None

        return _extract_results_google(html)

    except Exception as e:
        log.debug(f"Google error: {e}")
        return None
    finally:
        try:
            if page: page.close()
            if context: context.close()
        except Exception:
            pass


def _extract_results_google(html: str) -> list[tuple[str, str, str]]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    results: list[tuple[str, str, str]] = []
    seen_hosts: set[str] = set()

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
# ENGINE 2: Bing
# ─────────────────────────────────────────────────────────────────────────────

def _search_bing(query: str, browser, settings: Settings) -> list[tuple[str, str, str]] | None:
    """Search Bing via Playwright. Returns list of (url, title, snippet) or None."""
    ua = random.choice(_USER_AGENTS)
    encoded = quote_plus(query)
    url = f"https://www.bing.com/search?q={encoded}&count=20"

    page = None
    context = None
    try:
        page, context = _new_stealth_page(browser, ua)
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        time.sleep(random.uniform(2.0, 4.0))
        _human_behavior(page)
        html = page.content()

        # Check if Bing blocked us
        lower = html.lower()
        if "captcha" in lower or "verify you are human" in lower:
            print(f"  🚫 Bing also blocked!", flush=True)
            return None

        return _extract_results_bing(html)

    except Exception as e:
        log.debug(f"Bing error: {e}")
        return None
    finally:
        try:
            if page: page.close()
            if context: context.close()
        except Exception:
            pass


def _extract_results_bing(html: str) -> list[tuple[str, str, str]]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    results: list[tuple[str, str, str]] = []
    seen_hosts: set[str] = set()

    # Bing organic results: li.b_algo
    for li in soup.select("li.b_algo"):
        a_tag = li.select_one("h2 a[href^='http']")
        if not a_tag:
            a_tag = li.select_one("a[href^='http']")
        if not a_tag:
            continue
        href = a_tag.get("href", "").strip()
        if not href.startswith("http") or _is_blocked(href):
            continue
        host = _host(href)
        if host in seen_hosts:
            continue
        seen_hosts.add(host)
        title = a_tag.get_text(" ", strip=True)
        snippet_el = li.select_one(".b_caption p, .b_lineclamp2")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        results.append((href, title[:150], snippet[:200]))

    return results[:20]


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE 3: DuckDuckGo HTML (no API key, lightweight)
# ─────────────────────────────────────────────────────────────────────────────

def _search_ddg(query: str, browser, settings: Settings) -> list[tuple[str, str, str]] | None:
    """Search DuckDuckGo HTML version via Playwright."""
    ua = random.choice(_USER_AGENTS)
    encoded = quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded}"

    page = None
    context = None
    try:
        page, context = _new_stealth_page(browser, ua)
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        time.sleep(random.uniform(1.5, 3.0))
        html = page.content()

        return _extract_results_ddg(html)

    except Exception as e:
        log.debug(f"DDG error: {e}")
        return None
    finally:
        try:
            if page: page.close()
            if context: context.close()
        except Exception:
            pass


def _extract_results_ddg(html: str) -> list[tuple[str, str, str]]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    results: list[tuple[str, str, str]] = []
    seen_hosts: set[str] = set()

    for result in soup.select("div.result, div.web-result"):
        a_tag = result.select_one("a.result__a, a.result__url, h2 a")
        if not a_tag:
            a_tag = result.select_one("a[href^='http']")
        if not a_tag:
            continue
        href = a_tag.get("href", "").strip()
        # DDG sometimes uses redirect URLs
        if "duckduckgo.com" in href:
            continue
        if not href.startswith("http") or _is_blocked(href):
            continue
        host = _host(href)
        if host in seen_hosts:
            continue
        seen_hosts.add(host)
        title = a_tag.get_text(" ", strip=True)
        snippet_el = result.select_one("a.result__snippet, .result__snippet")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        results.append((href, title[:150], snippet[:200]))

    return results[:20]


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT — Cascading Fallback
# ─────────────────────────────────────────────────────────────────────────────

def discover_official_website(company_name: str, settings: Settings) -> GooglePick:
    """
    Discover official website URL using cascading search engines:
      ① Google (stealth) — skipped if previously blocked
      ② Bing
      ③ DuckDuckGo HTML
      ④ Skip (return None, don't block pipeline)
    """
    global _GOOGLE_BLOCKED

    name = " ".join(str(company_name).split()).strip()
    if not name:
        return GooglePick(None, "invalid_company", "empty name")

    if settings.mock_google:
        u = (settings.mock_website_url or "").strip()
        if u:
            return GooglePick(u, "mock_google", "MOCK_GOOGLE=true")
        return GooglePick(None, "mock_google_no_url", "MOCK_WEBSITE_URL empty")

    try:
        from bs4 import BeautifulSoup  # noqa
    except ImportError:
        return GooglePick(None, "missing_dep", "pip install beautifulsoup4")

    try:
        browser = _ensure_browser(settings)
    except Exception as e:
        return GooglePick(None, "browser_error", str(e)[:200])

    # Build query (just use variant 0 — company name quoted)
    query = build_search_query(name, variant=0)
    query_v2 = build_search_query(name, variant=1)

    # ─── Engine cascade ───
    engines = []
    if not _GOOGLE_BLOCKED:
        engines.append(("Google", _search_google))
    engines.append(("Bing", _search_bing))
    engines.append(("DuckDuckGo", _search_ddg))

    for engine_name, search_fn in engines:
        print(f"  🌐 {engine_name}: '{query}'", flush=True)

        results = search_fn(query, browser, settings)

        # If no results, try variant 2 query
        if not results:
            time.sleep(random.uniform(2, 4))
            results = search_fn(query_v2, browser, settings)

        if results is None:
            # Engine blocked/failed — try next
            print(f"  ⚠️  {engine_name} blocked/failed, trying next engine...", flush=True)
            time.sleep(random.uniform(2, 5))
            continue

        print(f"  📋 {engine_name}: {len(results)} links found", flush=True)

        if results:
            best, score, detail = pick_best_url(name, results)
            if best:
                print(f"  ✅ [{engine_name}] URL: {best}  (score={score:.1f})", flush=True)
                return GooglePick(best, "picked", f"{engine_name}; {detail}; score={score:.1f}")
            # Low confidence — use first result
            first_url = results[0][0]
            print(f"  ⚠️  [{engine_name}] Low confidence, using first: {first_url}", flush=True)
            return GooglePick(first_url, "low_confidence", f"{engine_name}; first_result; score={score:.1f}")

        # Empty results list (not None) — engine worked but found nothing, try next
        print(f"  📭 {engine_name}: 0 results, trying next...", flush=True)
        time.sleep(random.uniform(2, 4))

    # All engines failed
    print(f"  ❌ All engines failed for: '{name}' — SKIPPING", flush=True)
    return GooglePick(None, "all_engines_failed", "Google+Bing+DDG all failed; skipped")


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
