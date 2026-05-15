from __future__ import annotations

import logging
import random
import re
import time
import warnings
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

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
)

GOOGLE_CSE_ENDPOINT = "https://www.googleapis.com/customsearch/v1"
_CSE_NOT_CONFIGURED_LOGGED = False
# Shared cooldown when DDG returns 202 Ratelimit (stop hammering).
_RATELIMIT_UNTIL: float = 0.0


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


def _resolve_result_href(href: str) -> str | None:
    if not href:
        return None
    h = href.strip()
    if h.startswith("//"):
        h = "https:" + h
    try:
        parsed = urlparse(h)
        qs = parse_qs(parsed.query)
        if "uddg" in qs and qs["uddg"]:
            return unquote(qs["uddg"][0])
        if qs.get("q") and "url" in (parsed.path or "").lower():
            return unquote(qs["q"][0])
        if h.startswith("/url?"):
            inner = parse_qs(parsed.query).get("q", [None])[0]
            if inner:
                return unquote(inner)
    except Exception:
        pass
    if h.startswith("http://") or h.startswith("https://"):
        return h
    return None


def _duckduckgo_candidates_from_html(html: str) -> list[tuple[str, str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[tuple[str, str, str]] = []

    for result in soup.select("div.result, div.web-result"):
        a = result.select_one("a.result__a[href]")
        if not a:
            continue
        href = (a.get("href") or "").strip()
        title = a.get_text(" ", strip=True)
        snippet_el = result.select_one("a.result__snippet, div.result__snippet")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        resolved = _resolve_result_href(href)
        if resolved:
            out.append((resolved, title, snippet))

    if not out:
        for a in soup.select("a.result__a[href]"):
            href = (a.get("href") or "").strip()
            resolved = _resolve_result_href(href)
            if resolved:
                out.append((resolved, a.get_text(" ", strip=True), ""))

    return out


def _rank_hits(company_name: str, hits: list[dict]) -> GooglePick:
    tuples: list[tuple[str, str, str]] = []
    for h in hits:
        url = (h.get("href") or "").strip()
        if not url.startswith("http") or _is_blocked(url):
            continue
        tuples.append((url, str(h.get("title") or ""), str(h.get("body") or "")))
    if not tuples:
        return GooglePick(None, "no_usable_links", "all results filtered")
    best, score, detail = pick_best_url(company_name, tuples)
    if not best:
        return GooglePick(None, "low_confidence", detail)
    return GooglePick(best, "picked", f"{detail}; score={score:.1f}")


def _is_ratelimit_error(exc: BaseException | str) -> bool:
    msg = str(exc).lower()
    return "ratelimit" in msg or "rate limit" in msg or "202 ratelimit" in msg


def _wait_ddg_cooldown(settings: Settings) -> None:
    global _RATELIMIT_UNTIL
    now = time.time()
    if now < _RATELIMIT_UNTIL:
        wait = _RATELIMIT_UNTIL - now
        log.warning("DDG rate limit: waiting %.0f seconds before next search...", wait)
        time.sleep(wait)


def _mark_ddg_ratelimit(settings: Settings) -> None:
    global _RATELIMIT_UNTIL
    _RATELIMIT_UNTIL = time.time() + settings.ddg_ratelimit_cooldown_s
    log.warning(
        "DDG rate limit hit — pausing all searches for %.0f seconds.",
        settings.ddg_ratelimit_cooldown_s,
    )


def _ddg_api_search(company_name: str, query: str) -> GooglePick:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return GooglePick(None, "ddg_api_missing", "pip install duckduckgo-search")

    try:
        with DDGS() as ddgs:
            hits = list(ddgs.text(query, max_results=12, backend="bing"))
            if not hits:
                hits = list(ddgs.text(query, max_results=12, backend="auto"))
    except Exception as e:
        if _is_ratelimit_error(e):
            return GooglePick(None, "ddg_ratelimit", str(e))
        return GooglePick(None, "ddg_api_error", str(e))

    if not hits:
        return GooglePick(None, "ddg_no_results", "empty result set")
    return _rank_hits(company_name, hits)


def _ddg_html_search(company_name: str, query: str) -> GooglePick:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }
    with httpx.Client(timeout=35.0, follow_redirects=True) as client:
        r = None
        for attempt in range(4):
            r = client.get("https://html.duckduckgo.com/html/", params={"q": query}, headers=headers)
            if r.status_code == 202 and attempt < 3:
                time.sleep(2.5 * (attempt + 1))
                continue
            break
        assert r is not None
    if r.status_code != 200:
        return GooglePick(None, "ddg_http_error", f"status={r.status_code}")

    raw = _duckduckgo_candidates_from_html(r.text)
    tuples = [(u, t, s) for u, t, s in raw if not _is_blocked(u)]
    if not tuples:
        return GooglePick(None, "ddg_no_results", "html parsed but no links")
    best, score, detail = pick_best_url(company_name, tuples)
    if not best:
        return GooglePick(None, "low_confidence", detail)
    return GooglePick(best, "picked_ddg_html", f"{detail}; score={score:.1f}")


def _discover_duckduckgo(company_name: str, settings: Settings) -> GooglePick:
    """
    Free search via duckduckgo-search (v8+ often uses Bing — more stable than html/lite).
    One query per company by default; long cooldown on 202 Ratelimit.
    """
    _wait_ddg_cooldown(settings)
    delay = max(5.0, settings.ddg_delay_s)
    max_variants = max(1, min(3, settings.ddg_max_variants))
    last: GooglePick = GooglePick(None, "not_tried", "")

    for variant in range(max_variants):
        query = build_search_query(company_name, variant=variant)
        for attempt in range(max(1, settings.ddg_api_retries)):
            if attempt > 0:
                time.sleep(delay)

            pick = _ddg_api_search(company_name, query)

            if pick.status == "ddg_ratelimit":
                _mark_ddg_ratelimit(settings)
                return pick

            if pick.url:
                time.sleep(delay)
                return GooglePick(pick.url, f"picked_v{variant}", pick.detail)

            last = pick
            if pick.status == "low_confidence":
                break

        time.sleep(delay)

    if settings.ddg_use_html_fallback and last.status != "ddg_ratelimit":
        query = build_search_query(company_name, variant=0)
        time.sleep(delay)
        html_pick = _ddg_html_search(company_name, query)
        if html_pick.status == "ddg_http_error" and "202" in html_pick.detail:
            _mark_ddg_ratelimit(settings)
            return GooglePick(None, "ddg_ratelimit", html_pick.detail)
        if html_pick.url:
            return html_pick
        last = html_pick

    return last


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


def discover_official_website(company_name: str, settings: Settings) -> GooglePick:
    name = " ".join(str(company_name).split()).strip()
    if not name:
        return GooglePick(None, "invalid_company", "empty name")

    if settings.mock_google:
        u = (settings.mock_website_url or "").strip()
        if u:
            return GooglePick(u, "mock_google", "MOCK_GOOGLE=true")
        return GooglePick(None, "mock_google_no_url", "MOCK_WEBSITE_URL empty")

    provider = (settings.search_provider or "duckduckgo").strip().lower()
    if provider == "google":
        provider = "playwright"

    if provider == "cse":
        return _discover_via_google_cse(name, build_search_query(name), settings)

    if provider in ("duckduckgo", "ddg"):
        return _discover_duckduckgo(name, settings)

    cse_ready = bool((settings.google_cse_api_key or "").strip() and (settings.google_cse_cx or "").strip())
    global _CSE_NOT_CONFIGURED_LOGGED
    if provider == "auto" and cse_ready:
        cse = _discover_via_google_cse(name, build_search_query(name), settings)
        if cse.url:
            return cse
        return _discover_duckduckgo(name, settings)

    if not _CSE_NOT_CONFIGURED_LOGGED and provider == "auto":
        log.info("Using free DuckDuckGo search (no GOOGLE_CSE_* configured).")
        _CSE_NOT_CONFIGURED_LOGGED = True

    return _discover_duckduckgo(name, settings)
