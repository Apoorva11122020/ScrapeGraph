from __future__ import annotations


def build_search_query(company_name: str, *, variant: int = 0) -> str:
    """
    Query variants — ordered from broadest to most specific.
    variant 0: just company name (Google is smart enough)
    variant 1: company name + company
    variant 2: company name + official website
    """
    name = " ".join(str(company_name).split()).strip()
    if variant == 1:
        return f"{name} company"
    if variant == 2:
        return f"{name} official website"
    return name  # variant 0: just the name
