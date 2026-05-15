"""Client-approved extraction prompt and JSON schema for ScrapeGraphAI Extract."""

DEFAULT_EXTRACTION_PROMPT_TEMPLATE = """You are extracting data for this specific business only: "{expected_company_name}".

Extract the company name, up to 3 valid business email IDs, and up to 3 valid Indian mobile numbers from the website.

Check these locations when present: homepage, contact us page, header, footer, about us page, and any visible business contact sections.

Rules:
- Prefer official business contact details only.
- Return only valid business email IDs.
- Return only valid Indian 10-digit mobile numbers.
- Remove +91, spaces, dashes, and special characters from phone numbers (digits only, length 10).
- Ignore landline numbers, fax numbers, and toll-free numbers.
- Ignore duplicate emails and duplicate mobile numbers.
- If no data is found, leave fields blank.
- If a contact page exists, prioritize its content over the homepage content.
- If multiple numbers or emails are found across the website, include the best unique matches (up to 3 each).
- The company_name field must be the official name of "{expected_company_name}" or the closest match shown on this site — not a different company, brand, or government body.
"""


def build_extraction_prompt(expected_company_name: str) -> str:
    name = " ".join(str(expected_company_name).split()).strip() or "the business on this page"
    return DEFAULT_EXTRACTION_PROMPT_TEMPLATE.format(expected_company_name=name)

# Passed to the API as JSON Schema (v2 Extract). All string fields.
OUTPUT_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "company_name": {"type": "string", "description": "Official business name from the site."},
        "email1": {"type": "string"},
        "email2": {"type": "string"},
        "email3": {"type": "string"},
        "contact1": {"type": "string"},
        "contact2": {"type": "string"},
        "contact3": {"type": "string"},
    },
    "required": ["company_name", "email1", "email2", "email3", "contact1", "contact2", "contact3"],
}
