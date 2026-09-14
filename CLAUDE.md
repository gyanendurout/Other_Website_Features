# Project instructions — Feature Catalog

A competitive feature-intelligence catalog. It crawls websites, extracts their
features into SQLite, circles each feature on a screenshot, and compares sites
against each other. Crawling runs locally and free — no Firecrawl key, no LLM
key — and the results are published to Supabase and Vercel.

**`REQUIREMENTS.md` is the operating runbook. Read it before doing any work on
this project.** `README.md` covers architecture and the reasoning behind the
design. `docs/DEPLOY.md` covers the hosted copy.

## Local vs published

The **pipeline** is still local and free: Docker Firecrawl, crawl4ai,
Playwright, two SQLite files, no API keys, no spend. That has not changed.

The **web app** now reads Postgres on Supabase rather than the SQLite files, so
`next dev` needs `DATABASE_URL` in `web/.env.local`. Speaking one SQL dialect
instead of two was a deliberate trade — the closing section of `docs/DEPLOY.md`
says why.

Local results reach the internet with two idempotent commands, never by hand:

```powershell
.venv\Scripts\python.exe scripts\publish.py        # SQLite -> Postgres
.venv\Scripts\python.exe scripts\upload_plates.py  # WebP -> Storage
```

Both are safe to re-run; they update what moved and skip everything else.

---

## "Start the server"

When the user says **start the server** (or start/run/boot the app, the stack,
the site, the project), that means one command:

```powershell
.\start.ps1
```

This starts Docker Desktop if needed, brings up all five Firecrawl containers,
waits for the API on `:3002`, kills any stale listener on `:3100`, starts
`next dev`, and prints the catalog totals. It is idempotent.

Do **not** hand-run `docker compose up` or `npm run dev` separately — that is
what `start.ps1` is for, and doing it piecemeal is how the `.next` conflict and
the RabbitMQ race got hit before.

- `.\start.ps1 -Rebuild` — also wipes `web/.next`
- `.\start.ps1 -NoWeb` — containers only
- `.\stop.ps1` — stop everything (data is kept; the DB is on the host)

"Stop the server" means `.\stop.ps1`.

---

## "Here's a website" — add it to the catalog

Follow **§3 of `REQUIREMENTS.md`** exactly. Summary:

1. `scripts\capture.py --url <url> --name "<Name>"` — then **check which pages
   it picked**. Auto-discovery sorts by path length and sometimes chooses badly
   (it once picked a logo towel as the flagship product page). Scrape better
   pages by hand if so.
2. `scripts\c4a_scrape.py <homepage>` — Firecrawl strips nav, crawl4ai keeps it.
   Always run both on the homepage.
3. Read the markdown, write `data/raw/<domain>.json`, load with
   `scripts\add_features.py`.
4. `scripts\annotate.py --site <domain> --wait 3000`
5. Verify any negative finding with `scripts\verify.py <url>` before reporting it.

### Non-negotiable rules

- **`evidence` must be ONE contiguous run of text as it appears in the DOM.**
  Never join separate elements with `-`, `...`, `|` or `/`. Composite quotes
  read well and match nothing. Diagnose with `scripts\query.py --failed <domain>`.
- **Reuse existing canonical names.** Check `scripts\query.py --canonical` first.
  Comparison keys on the canonical slug; a new synonym invents a fake gap.
- **Markdown absence is not absence.** Client-side widgets (reviews, chat,
  personalisation) are invisible to the scrape. Run `scripts\verify.py` before
  claiming a site lacks a feature. This has produced a wrong headline finding
  once already.
- **Never invent evidence from a URL slug.** If it is only in the site map, say
  so in the description and set `confidence` ≤ 0.7.

- **Compare the clean plate against the annotated one after every run.**
  `annotate.py` writes `<page>-clean.png` first and cuts the crops from
  `<page>.png`. A popup that arrives between the two ruins only the second, and
  the run still prints a healthy `8/12 circled` — GAMMA shipped nine solid-white
  crops that way. Check file size and mean brightness, not just the count.

---

## Politeness — these are live third-party sites

- Space requests out. ~15 automated hits in 30 minutes triggered a Cloudflare
  block on one site and took everything down with it.
- If `annotate.py` prints `BLOCKED`, **stop and wait**. Never retry in a loop.
- Never click page controls during capture. `JS_DISMISS` removes overlays rather
  than clicking them, and `JS_EXPAND` refuses anything matching
  `add to cart|buy|checkout|subscribe|pay` or inside a `<form>`. This exists
  because an early version added an item to a live store's cart.

---

## Environment notes

- **PowerShell 5.1**: never `2>&1` a native executable — stderr becomes
  ErrorRecords and a harmless docker warning turns fatal. Test `$LASTEXITCODE`.
- Use `C:/...` paths for Python, not git-bash `/c/...` paths.
- Windows console is cp1252; scripts already reconfigure stdout to UTF-8.
- The web app uses `node:sqlite` (Node 22+) deliberately, to avoid compiling
  `better-sqlite3` on Windows. It returns null-prototype rows, which React
  Server Components reject — `web/lib/db.ts` re-wraps every row.

## Ports

| | |
|---|---|
| `3100` | Next.js web UI |
| `3002` | Firecrawl API (`/` is liveness; `/test` 404s) |
