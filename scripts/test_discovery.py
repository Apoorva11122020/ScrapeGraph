import time
from dataclasses import replace

from scrape_ai_workflow.google_discovery import discover_official_website
from scrape_ai_workflow.settings import load_settings

s = replace(
    load_settings(),
    mock_google=False,
    search_provider="duckduckgo",
    ddg_delay_s=2.5,
)
names = [
    "JMR Apprals",
    "DL International",
    "Sekar Leather",
    "White House",
    "Sartoga Tex Pvt.Ltd.",
]
for name in names:
    g = discover_official_website(name, s)
    url = (g.url or "NONE")[:65]
    print(f"{name:22} -> {url:65} | {g.status}")
    time.sleep(2)
