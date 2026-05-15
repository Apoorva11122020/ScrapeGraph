from __future__ import annotations


def build_search_query(company_name: str, *, variant: int = 0) -> str:
    """
    Search queries for Indian export / textile SMBs. variant 0..2 = progressively simpler.
    """
    name = " ".join(str(company_name).split()).strip()
    if variant == 1:
        return f"{name} India company official website"
    if variant == 2:
        return f"{name} India exporter contact"
    return f"{name} India textile export company website"
