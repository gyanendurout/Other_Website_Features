# Going online — Supabase + Vercel

## Status — 14 Sept 2026

Supabase is **live and verified**. Vercel and GitHub are not done yet.

| | |
|---|---|
| Project | `vbyaqzkagzhatdqitfko` · region **ap-northeast-2 (Seoul)** |
| Schemas | `catalog` (7 tables) · `pdp` (7 tables) · 22 indexes and 2 views each |
| Rows | 2,535 published — every count matches the local SQLite exactly |
| Storage | bucket `plates`, public, **695 objects / 43 MB** (from 693 MB of PNG) |
| App role | `catalog_read` — SELECT only, writes refused, verified through the pooler |
| Verified | all 13 routes 200, no broken images, no console errors, overlays correct |

Local production build against Supabase, measured with curl:

```
/                0.19s      /pdp              0.29s
/screens         0.17s      /pdp/matrix       0.39s
/compare         0.23s      /pdp/drinkag1.com 0.65s
/gaps            0.31s      /sites/joola.com  0.83s
/search          0.30s      /features         0.95s   (870 KB of HTML)
```

**Pick the Vercel region deliberately.** The database is in Seoul. Vercel
defaults to `iad1` (Washington DC), which would put roughly 200 ms of round trip
between the function and Postgres on *every query* — and these pages issue three
or four each. Set the function region to **`icn1` (Seoul)** to match. This is the
single biggest performance decision left in the deployment.

### Still to do

1. Push to GitHub (repo is committed locally on `main`)
2. Import to Vercel — Root Directory `web`, region `icn1`, three env vars below
3. **Rotate both credentials that were shared in chat**: the `sb_secret_…` key
   (Settings → API) and the database password (Settings → Database). The app
   itself uses `catalog_read`, so rotating the `postgres` password does not
   break the site — only `publish.py`, which is run by hand anyway.

---


The local pipeline does not change: `start.ps1`, `capture.py`, `annotate.py` and
the two SQLite files all keep working exactly as `REQUIREMENTS.md` describes.
What changes is that the **web app now reads Postgres**, and one command
publishes local results to it.

```
LOCAL (unchanged)                              ONLINE
  capture.py ─┐
  annotate.py ─┼─► db/features.db ─┐
  firecrawl   ─┘   db/pdp.db       ├─► publish.py ──► Supabase Postgres ─┐
                   data/screenshots ┘                                    ├─► Vercel
                        │                                                │
                        └─► to_webp.py ──► upload_plates.py ──► Storage ─┘
```

---

## One-time setup

### 1. Supabase project

Create a project, then **Project Settings → Database → Connection string**. You
need two different URIs and they are not interchangeable:

| Use | Which URI | Port |
|---|---|---|
| `psql`, `publish.py` (DDL + bulk insert) | Session pooler *or* Direct | 5432 |
| The web app on Vercel | **Transaction** pooler | 6543 |

The transaction pooler is what makes hundreds of short-lived serverless
functions survivable, and it is why `web/lib/pg.ts` sets `prepare: false` —
transaction mode hands the same backend connection to different clients between
statements, so a server-side prepared statement belongs to whoever gets it next.
Using the direct URI on Vercel works in testing and exhausts connections under
real traffic.

### 2. Schema

```powershell
$env:DATABASE_URL = "postgresql://...5432/postgres"   # session or direct
psql $env:DATABASE_URL -f supabase/schema.sql
```

Creates schemas `catalog` and `pdp`. Re-runnable — every statement is
`IF NOT EXISTS` or `OR REPLACE`.

No `psql` on the machine? Paste the file into the Supabase SQL Editor instead.

### 3. Storage bucket

Supabase dashboard → **Storage → New bucket**:

- Name: `plates`
- **Public: on** — the plates are screenshots of public marketing pages, and a
  public bucket means the app needs no key in the browser and the CDN can cache

### 4. Publish the data

```powershell
$env:DATABASE_URL = "postgresql://...5432/postgres"
.venv\Scripts\python.exe scripts\publish.py --dry-run    # row counts, no writes
.venv\Scripts\python.exe scripts\publish.py
```

Expected:

```
catalog   sites 7    pages 24   canonical 94    features 361  links 339  annotations 361
pdp       sites 13   pages 13   canonical 132   features 417  links 417  annotations 357
```

### 5. Publish the plates

```powershell
.venv\Scripts\python.exe scripts\to_webp.py              # 693 MB -> 45 MB
.venv\Scripts\python.exe scripts\upload_plates.py --check

$env:SUPABASE_URL = "https://<ref>.supabase.co"
$env:SUPABASE_SERVICE_KEY = "<service_role key>"
.venv\Scripts\python.exe scripts\upload_plates.py
```

`--check` first, always. A plate the database references but the bucket lacks
renders as a broken image with no error anywhere — this is the only thing that
catches it.

The `service_role` key bypasses row-level security. It goes in your shell for
this one command and **never** into the repo, the browser, or Vercel.

### 6. GitHub

This directory is not yet a git repository. `.gitignore` already excludes the
things that must not be published — `data/` (693 MB of PNG), `db/*.db`, `.venv/`
and `firecrawl/`, which holds a real `.env`.

```powershell
git init
git add .
git status                 # confirm no data/, db/, .venv/ or firecrawl/
git commit -m "feat: publish catalog to Supabase + Vercel"
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

Check `git status` before committing. Once 693 MB of PNG is in the history it
does not come out without a rewrite.

### 7. Vercel

Import the repo, then:

| Setting | Value |
|---|---|
| **Root Directory** | `web` |
| Framework | Next.js (auto-detected) |

Environment variables:

| Name | Value |
|---|---|
| `DATABASE_URL` | the **transaction** pooler URI, port **6543** |
| `NEXT_PUBLIC_SUPABASE_URL` | `https://<ref>.supabase.co` |
| `CATALOG_READONLY` | `1` |

`CATALOG_READONLY=1` turns `/capture` into an explanation instead of a form, and
makes the capture API return 403. The pipeline it drives needs Docker, Python
and Playwright; Vercel has none of them, so a job queued there would be a row
nothing ever picks up.

---

## After every future crawl

```powershell
.\start.ps1
# ... capture.py / add_features.py / annotate.py as usual ...

$env:DATABASE_URL = "postgresql://...5432/postgres"
$env:SUPABASE_URL = "https://<ref>.supabase.co"
$env:SUPABASE_SERVICE_KEY = "<service_role key>"

.venv\Scripts\python.exe scripts\publish.py
.venv\Scripts\python.exe scripts\to_webp.py
.venv\Scripts\python.exe scripts\upload_plates.py
```

Both are idempotent: `publish.py` upserts and `to_webp.py` skips anything
already converted, so re-running costs seconds and changes only what moved. No
redeploy is needed — the site reads the database live.

---

## Local development after the move

`next dev` now needs `DATABASE_URL` too, because the app speaks one SQL dialect
rather than two. Put it in `web/.env.local` (git-ignored):

```
DATABASE_URL=postgresql://...6543/postgres
NEXT_PUBLIC_SUPABASE_URL=https://<ref>.supabase.co
```

**This is a real change to a stated project value.** `CLAUDE.md` opens with
"Everything runs locally and free". Capture still is — no Firecrawl key, no LLM
key, no spend. But *viewing* the catalog now needs the network. Keeping a SQLite
path alive as well would mean maintaining two SQL dialects across ~25 queries
(`?` vs `$1`, `GROUP_CONCAT` vs `string_agg`, FTS5 vs `tsvector`), which is a
standing source of bugs that only appear in one environment. One dialect was the
better trade, and it is worth knowing it was a trade.

---

## Verify before calling it done

1. `/` reads **7 sites · 361 features · 24 pages · 317 pinned** — the same
   numbers `stats.py` has printed all along
2. `/pdp` reads **13 sites · 417 features · 310 circled**
3. No PDP-Lab domain appears on `/`, `/features`, `/screens`, `/compare`,
   `/gaps` or `/search` — the two schemas are the whole isolation mechanism
4. `/pdp/drinkag1.com` renders its plate **and** circle ① sits on
   "$49 billed every 30 days" — proof the DPR-1 conversion kept the geometry
5. `/search` returns results — proof the FTS5 → `tsvector` port works
6. `/capture` shows the read-only explanation, not a form

### If every circle is in the wrong place

`scripts/to_webp.py` serves plates at DPR 1 and `SCALE` in
`web/app/pdp/[domain]/plate.tsx` and `web/app/screens/[id]/viewer.tsx` is `1` to
match. They are one decision written in two languages. If `HALVE` changes and
`SCALE` does not, every circle moves and nothing reports an error.
