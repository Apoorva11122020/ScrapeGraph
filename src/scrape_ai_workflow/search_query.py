from __future__ import annotations


def build_search_query(company_name: str, *, variant: int = 0) -> str:
    """
    Keep queries short — long queries often return empty results from DDG/Bing API.
    """
    name = " ".join(str(company_name).split()).strip()
    if variant == 1:
        return f"{name} India exporter contact"
    if variant == 2:
        return f"{name} official website India"
    return f"{name} India company website"
