import re
from urllib.parse import unquote

import httpx

q = "JMR Apprals official website"
r = httpx.get(
    "https://html.duckduckgo.com/html/",
    params={"q": q},
    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    timeout=30,
    follow_redirects=True,
)
print("status", r.status_code, "len", len(r.text))
urls = [unquote(m.group(1)) for m in re.finditer(r"uddg=([^&\"]+)", r.text)]
print("found", len(urls))
for u in urls[:10]:
    print(u)
