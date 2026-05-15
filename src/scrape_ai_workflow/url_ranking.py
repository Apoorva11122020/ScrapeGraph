from __future__ import annotations

import re
from difflib import SequenceMatcher
from urllib.parse import urlparse

_DIRECTORY_HOSTS = (
    "dnb.com",
    "thecompanycheck.com",
    "falconebiz.com",
    "tradeindia.com",
    "indiamart.com",
    "justdial.com",
    "zaubacorp.com",
    "tofler.in",
    "exportersindia.com",
    "sulekha.com",
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "wikipedia.org",
    "springer.com",
    "bing.com",
)

# Wrong-site magnets for generic names.
_HOST_PENALTY_UNLESS_MATCH = (
    "whitehouse.gov",
    "delta.com",
    "tods.com",
    "starhealth.in",
    "starhealth.com",
    "nike.com",
    "apple.com",
    "microsoft.com",
    "amazon.com",
)

# Host patterns that are almost never a company's own marketing site.
_HOST_HARD_BLOCK = (
    ".ac.in",
    ".edu",
    ".gov.in",
    ".nic.in",
    "google.com",
    "gstatic.com",
)

_STOPWORDS = frozenset(
    {
        "pvt",
        "ltd",
        "limited",
        "private",
        "company",
        "co",
        "corp",
        "corporation",
        "inc",
        "llp",
        "india",
        "indian",
        "the",
        "and",
        "of",
        "exports",
        "export",
        "international",
        "tex",
        "textile",
        "textiles",
        "studio",
        "overseas",
        "labs",
        "furnish",
        "furnishing",
        "embroidery",
        "leather",
        "apprals",
        "apparel",
        "pl",
    }
)

MIN_ACCEPT_SCORE = 3.0


def company_tokens(company_name: str) -> list[str]:
    raw = re.split(r"[^a-z0-9]+", company_name.casefold())
    out: list[str] = []
    for t in raw:
        if len(t) < 3 or t in _STOPWORDS:
            continue
        out.append(t)
    if not out:
        for t in raw:
            if len(t) >= 2 and t not in _STOPWORDS:
                out.append(t)
    return out


def _host(url: str) -> str:
    try:
        return urlparse(url).netloc.casefold().replace("www.", "")
    except Exception:
        return ""


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.casefold(), b.casefold()).ratio()


def _token_in_host(tok: str, host: str) -> bool:
    """Match domain labels; short tokens must be a label prefix (dl → dlinternational.com)."""
    host = host.replace("www.", "")
    labels = [lb for lb in re.split(r"[.\-]", host) if lb]
    labels_flat = "".join(labels)
    if tok in labels:
        return True
    if len(tok) >= 4 and tok in labels_flat:
        return True
    if len(tok) <= 3:
        for label in labels:
            if label.startswith(tok) and len(label) >= len(tok) + 3:
                return True
        return False
    return tok in host


def _host_token_matches(host: str, tokens: list[str]) -> int:
    n = sum(1 for tok in tokens if _token_in_host(tok, host))
    if len(tokens) >= 2:
        initials = "".join(t[0] for t in tokens if t)
        host_flat = host.replace("-", "").replace(".", "")
        if len(initials) >= 3 and initials in host_flat:
            n += 1
    return n


def score_candidate(
    company_name: str,
    url: str,
    *,
    title: str = "",
    snippet: str = "",
) -> float:
    host = _host(url)
    if not host:
        return -100.0

    for block in _HOST_HARD_BLOCK:
        if block in host:
            return -100.0

    tokens = company_tokens(company_name)
    blob = f"{host} {title} {snippet}".casefold()
    score = 0.0
    host_matches = _host_token_matches(host, tokens)

    for tok in tokens:
        if _token_in_host(tok, host):
            score += 5.0
        elif tok in blob:
            score += 1.0

    if host_matches >= 2:
        score += 4.0
    elif host_matches == 1 and len(tokens) == 1:
        score += 2.0

    if host.endswith(".in") or host.endswith(".co.in"):
        score += 1.5

    if any(x in blob for x in ("textile", "garment", "apparel", "export", "leather", "furnish", "manufacturer")):
        score += 0.5

    for d in _DIRECTORY_HOSTS:
        if d in host:
            score -= 10.0
            break

    for bad in _HOST_PENALTY_UNLESS_MATCH:
        if bad in host:
            if host_matches < 2:
                score -= 20.0
            break

    # Single generic token matching a huge unrelated brand domain (e.g. "star" -> starhealth)
    if host_matches == 1 and len(tokens) >= 2 and score < 6:
        score -= 5.0

    # Must have at least one token reflected in hostname for acceptance (except 1-token companies)
    if tokens and host_matches == 0:
        score -= 8.0

    return score


def pick_best_url(
    company_name: str,
    candidates: list[tuple[str, str, str]],
) -> tuple[str | None, float, str]:
    if not candidates:
        return None, 0.0, "no_candidates"

    scored: list[tuple[float, str, str]] = []
    for url, title, snippet in candidates:
        s = score_candidate(company_name, url, title=title, snippet=snippet)
        if s <= -50:
            continue
        scored.append((s, url, f"score={s:.1f} host={_host(url)[:45]}"))

    if not scored:
        return None, 0.0, "all_candidates_blocked"

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_url, detail = scored[0]
    if best_score < MIN_ACCEPT_SCORE:
        top3 = "; ".join(x[2] for x in scored[:3])
        return None, best_score, f"below_threshold({MIN_ACCEPT_SCORE}): {top3}"

    return best_url, best_score, detail


def names_likely_match(expected: str, extracted: str) -> bool:
    e = " ".join(str(expected).split()).strip()
    x = " ".join(str(extracted).split()).strip()
    if not e:
        return True
    if not x:
        return True
    if _similarity(e, x) >= 0.55:
        return True
    et = set(company_tokens(e))
    xt = set(company_tokens(x))
    if et and xt and len(et & xt) >= 1:
        return True
    return False
