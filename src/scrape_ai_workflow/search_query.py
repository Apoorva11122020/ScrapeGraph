from __future__ import annotations


def build_search_query(company_name: str, *, variant: int = 0) -> str:
    """
    Keep queries short and broad — don't force "India" as company may be global.
    """
    name = " ".join(str(company_name).split()).strip()
    if variant == 1:
        return f"{name} official website"
    if variant == 2:
        return f"{name} company"
    return f"{name} website"
