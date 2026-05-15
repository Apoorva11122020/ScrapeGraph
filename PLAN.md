# Company → Google → ScrapeGraphAI → Excel — Implementation Plan (Hinglish)

Yeh document tumhari bid ke workflow ko **order mein** break karta hai, taaki **limited API credits** bacha kar pehle sab kuch land kar sako, aur **ScrapeGraphAI sirf end mein** test karo.

---

## Goal (one line)

Excel se company names → har name ke liye **official website URL** discover karo (Google via Playwright/Selenium) → URL ko ScrapeGraphAI Extract API pe bhejo (prompt + schema + key) → emails + Indian mobiles structured XLSX/CSV mein likho, **missed rows bhi blank fields + status** ke saath retain karo.

---

## Constraints (client + tumhari choice)

| Item | Note |
|------|------|
| Credits | Demo ~475; ~5 credits/company max — trial 90 pe tight; **API calls end tak postpone** sensible hai. |
| URL only | Script sirf **base website URL** resolve kare; “Contact Us” priority **extraction prompt** mein already hai. |
| Scale later | ~20k — isliye **checkpoint, resume, logging** non-negotiable. |

---

## Phase order (API last — recommended)

Is sequence se **zyaada tar code** bina live ScrapeGraph calls ke test ho jayega.

### Phase 0 — Repo + env skeleton (½ day)

1. Python 3.11+ venv, `requirements.txt` (pandas, openpyxl, httpx/requests, playwright ya selenium, python-dotenv).
2. `.env.example` — `SCRAPEGRAPH_API_KEY`, optional `GOOGLE_*`, proxy vars (placeholder).
3. Folder layout suggestion: `src/`, `config/`, `data/input/`, `data/output/`, `logs/`, `checkpoints/`.

**Done when:** `pip install -r requirements.txt` + `playwright install chromium` (agar Playwright) clean chal jaye.

---

### Phase 1 — Excel I/O + column contract (½ day)

1. Input: client sheet — **SR NO, COMPANY NAME (col B), row 3 se data** (header row 2); code mein **header-based mapping** prefer karo taaki column shift se break na ho.
2. Output columns minimum: `sr_no`, `company_name`, `website_url`, `email1..3`, `contact1..3`, `status`, `error_detail`, `scraped_at` (optional `credits_used` jab API on ho).
3. **Har row output mein rahe** — success ho ya na ho; blanks + status for manual review.

**Done when:** Dummy input se dummy output XLSX/CSV generate ho, bina API ke.

---

### Phase 2 — Checkpoint + resume (½ day)

1. Har N rows (e.g. 10) ke baad **checkpoint JSON/Parquet/SQLite** — last processed `row_index` + partial results.
2. Rerun par: checkpoint se **skip processed**, idempotency (same company duplicate na ho).

**Done when:** Process mid-way kill karke dubara run — resume sahi rows se shuru ho.

---

### Phase 3 — Google URL discovery (Playwright preferred) (1–2 days)

**Yeh phase sabse risky (CAPTCHA); isko API se pehle solid karna worth hai.**

1. Flow: Google search query e.g. `"{company_name}" official website` → **organic results** parse → heuristics:
   - google/maps/youtube/facebook/linkedin/indiamart/justdial ko **default exclude** (toggle config se allow kar sakte ho).
   - Pehla “reasonable” domain pick + optional **title/snippet** match score.
2. **Mock mode:** `MOCK_SERHTML=1` ya fixture HTML files se parser test — **zero Google hits**, fast CI-style check.
3. **Human-like pacing:** random delay (e.g. 2–8s) + daily cap env se; same session reuse thoughtfully.
4. **Proxy hooks:** env-based HTTP proxy for browser agar client baad mein de.
5. Logging: `no_results`, `captcha_detected`, `blocked`, `picked_url`, `confidence`.

**Done when:** Mock + chhota live smoke (5–10 queries) se URLs mil rahe hain; CAPTCHA aaye to log + status clear.

---

### Phase 4 — ScrapeGraphAI client (stub + dry-run) (½ day) — **bina credits burn kiye**

1. `extract_client.py`: function `call_extract(url, prompt, schema) -> dict`.
2. **`DRY_RUN=true`** mode: real HTTP skip, **fixed sample JSON** return karo — end-to-end pipeline Excel tak chalao.
3. Request body dashboard / docs ke hisaab se exact keys (website URL field name confirm karna).

**Done when:** Full pipeline: Excel → “fake Google” ya small real Google → **dry-run API** → output file + summary counts.

---

### Phase 5 — Rate limit, retry, summary report (½ day)

1. Retries: sirf **network 5xx / timeout** par exponential backoff; **4xx / quota** par aggressive retry mat karo (credits + ban risk).
2. Summary JSON/txt end mein: total, `url_found`, `extract_ok`, `extract_failed`, `skipped_duplicate`, CAPTCHA count.

**Done when:** Dry-run par summary sahi numbers de.

---

### Phase 6 — Real ScrapeGraphAI integration test (jab tum ready ho) (½ day)

1. `DRY_RUN=false`, pehle **1 company**, phir **5**, phir poora trial batch.
2. Schema keys lock: `company_name`, `email1..3`, `contact1..3` — API response ko normalize (missing keys → `""`).
3. Credits track: agar response mein metadata mile to log; warna manual estimate document kar dena.

**Done when:** Client ke trial sheet par meaningful fill rate + stable failures logged.

---

### Phase 7 — Polish deliverables (½ day)

1. README: install, env vars, commands (`python -m src.main --input ... --output ...`), resume behaviour, mock/dry-run flags.
2. `requirements.txt` pin versions (rough OK for v1).
3. Final handover: sample output + processing summary template.

---

## CAPTCHA / scale mitigation (short)

- Randomized delays + session discipline; **burst avoid**.
- Rotating **residential** proxies agar volume badhe (datacenter often jaldi flag).
- Optional CAPTCHA solver — **legal/ToS** client ko clarify; default mein off.
- Long-term maintainability: **Google Custom Search JSON API** alternative ek section README mein mention (paid but predictable) — client ko choice dena.

---

## Timeline (realistic, parallel where possible)

| Window | Kaam |
|--------|------|
| Day 1 | Phase 0–2 + Excel contract |
| Day 2–3 | Phase 3 (discovery + mock) heavy |
| Day 4 | Phase 4–5 dry-run E2E |
| Day 5 | Phase 6 live API trial + Phase 7 docs |

CAPTCHA zyada aaya to Phase 3 extend; API phase tab tak block nahi honi chahiye agar dry-run strict use ho.

---

## Daily “definition of done” (fast closure ke liye)

- Har din end: **one command** se pipeline chale (mock/dry-run), **checkpoint + log file** mile.
- API key `.env` mein; **git mein commit mat** karna.

---

## Risk register (client ko optional share)

| Risk | Mitigation |
|------|------------|
| Google CAPTCHA | Delays, proxies, reduce QPS, fallback Custom Search API |
| Wrong official URL | Heuristics + optional manual review column `url_confidence` |
| Credit exhaust mid-run | Checkpoint + resume + retry caps |
| API schema drift | Single `normalize_response()` function + tests on fixtures |

---

## Next action (tumhare liye abhi)

1. Is `PLAN.md` ko apni bid / internal tracker se link kar lo.
2. Repo mein Phase 0–2 implement karo; **ScrapeGraph tab tak sirf stub/dry-run**.
3. Jab “sab green” ho tab hi `.env` mein real key se Phase 6.

---

*Document version: 1.0 — ScrapeAI project folder.*
