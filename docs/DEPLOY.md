# Going online — Supabase + Vercel

## Status — 14 Sept 2026

Supabase is **live and verified**. GitHub is **pushed** —
[gyanendurout/Other_Website_Features](https://github.com/gyanendurout/Other_Website_Features).
Vercel is the remaining step.

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

**The region is pinned, and it matters.** The database is in Seoul. Vercel
defaults to `iad1` (Washington DC), which puts roughly 200 ms of round trip
between the function and Postgres on *every query* — and these pages issue three
or four each. The first deployment ran in `iad1`; `web/vercel.json` now pins
`icn1` (Seoul) so this cannot regress. `/api/health` echoes `VERCEL_REGION`, so
it can be verified rather than assumed.

### Still to do

1. Import to Vercel — **two** manual actions, listed in §7
2. **Rotate all three credentials that were shared in chat.** Do this *after*
   the deploy is confirmed working, so a rotation and a deployment are not being
   debugged at the same time.

   | Credential | Where | What breaks |
   |---|---|---|
   | `sb_secret_…` key | Settings → API | `upload_plates.py` only |
   | `postgres` password | Settings → Database | `publish.py` only |
   | `catalog_read` password | Database → Roles | **the live site** |

   The first two are run by hand and never touch the deployment. `catalog_read`
   is the one the site authenticates as, so rotating it means updating
   **both** Vercel's `DATABASE_URL` and `web/.env.local` in the same pass —
   change one and the other silently serves `28P01`.

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

### 6. GitHub — done

Pushed to
[gyanendurout/Other_Website_Features](https://github.com/gyanendurout/Other_Website_Features).
`.gitignore` excludes the things that must not be published — `data/` (693 MB of
PNG), `db/*.db`, `.venv/` and `firecrawl/`, which holds a real `.env` — and the
published tree was checked against it: 143 files, no secret in any commit.

Check `git status` before committing. Once 693 MB of PNG is in the history it
does not come out without a rewrite.

### 7. Vercel — two manual actions, everything else is committed

Most of this configuration now lives in the repository, because the first
deployment failed three times in a row on settings that had to be typed into a
dashboard and were silently wrong each time.

| Committed | Where |
|---|---|
| Framework preset (Next.js) | `web/vercel.json` |
| Function region (`icn1`) | `web/vercel.json` |
| `NEXT_PUBLIC_SUPABASE_URL` | `web/.env.production` |
| `CATALOG_READONLY=1` | `web/.env.production` |

Neither committed variable is a credential: the Supabase URL appears in every
public plate URL the browser already requests, and `CATALOG_READONLY` is a
behaviour flag — the real enforcement is that the app authenticates as
`catalog_read`, a role with SELECT and nothing else.

`CATALOG_READONLY=1` turns `/capture` into an explanation instead of a form, and
makes the capture API return 403. The pipeline it drives needs Docker, Python
and Playwright; Vercel has none of them, so a job queued there would be a row
nothing ever picks up.

What still has to be done by hand:

**1. Root Directory → `web`.** This is the one setting that cannot be committed.
Vercel reads it *before* it reads any file in the repository, so no file in the
repository can influence it. The root has no `package.json`, so pointing Vercel
at `./` makes it detect no framework, publish the repo as static files in about
four seconds, and 404 every path. `index.html` at the repo root exists to catch
exactly that: if you ever see a page explaining the Root Directory setting, that
is what has happened. A real build takes roughly half a minute.

**2. `DATABASE_URL`.** It carries a password, so it belongs in Vercel's
encrypted environment variables and nowhere else. Scope it to Production *and*
Preview. Take the value from `web/.env.local` via the clipboard — never retype
it, and never rebuild it from a template plus a password found in a chat log:

```powershell
$u = (Get-Content web\.env.local | Where-Object { $_ -match '^DATABASE_URL=' } | Select-Object -First 1) -replace '^DATABASE_URL=',''
Set-Clipboard -Value $u.Trim()
"length : $($u.Trim().Length)"     # 134 for the current credential
```

A wrong length is the whole diagnosis. Everything except the password is 102
characters, so a 123-character string means a 21-character password — which is
the `postgres` user's, not `catalog_read`'s. That mistake authenticates against
the right host with the wrong role's secret and returns `28P01`.

Then **redeploy**. Vercel does not apply new environment variables to an
existing deployment, and `NEXT_PUBLIC_*` is inlined at build time.

### If it does not come up

Open `/api/health`. It runs the same connection the pages do and reports the
cause rather than a digest — whether `DATABASE_URL` arrived, whether the URI
reached the transaction pooler, and what Postgres said if it refused. Every page
that fails now renders that link instead of "Application error: a server-side
exception has occurred".

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
