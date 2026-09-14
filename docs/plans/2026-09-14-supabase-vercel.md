# Online Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Publish the Feature Catalog and PDP Lab on the internet — Postgres on
Supabase, Next.js on Vercel, plates in Supabase Storage — while the capture
pipeline keeps running locally and pushes results up.

**Architecture:** One Supabase Postgres database with **two schemas**,
`catalog` and `pdp`, preserving exactly the isolation the two SQLite files give
today. The Next.js app talks to it through `postgres.js` over Supabase's
transaction pooler. Screenshots convert to WebP (695 MB → target ~100 MB) and
move to a public Storage bucket. The hosted site is **read-only**: `capture.py`,
`annotate.py` and Firecrawl stay on the local machine, and one idempotent
`publish.py` pushes rows and images to Supabase.

**Tech Stack:** Supabase (Postgres 15 + Storage), Vercel, Next.js 15 App Router,
`postgres.js`, `psycopg[binary]`, Pillow.

---

## The decision that shapes everything

The web app currently opens two SQLite files with `node:sqlite` at
`../db/features.db` and `../db/pdp.db`. On Vercel that path does not exist and
the filesystem is read-only, so this is not a configuration change — the data
layer is replaced. Two properties must survive the move:

1. **Catalog isolation.** `getStats()` is `SELECT COUNT(*) FROM sites` with no
   filter. Merging the two catalogs into one set of tables would silently change
   every number on Overview, Features, Screens, Compare, Gaps and Search. Two
   Postgres schemas keep them apart for free, and `luzzpickleball.com` continues
   to exist independently in both.
2. **Annotation geometry.** `plate.tsx` and `viewer.tsx` compute CSS pixels as
   `naturalWidth / 2`, because plates are captured at `device_scale_factor = 2`.
   **WebP conversion must preserve pixel dimensions.** Downscaling to save bytes
   moves every circle on every page, and it fails silently — the circles just
   land in the wrong place.

### What this costs

`CLAUDE.md` opens with "Everything runs locally and free — no Firecrawl key, no
LLM key." After this migration that is still true of *capture*, but no longer
true of *viewing*: `next dev` will need the Supabase connection string, because
the app speaks one dialect, not two. Keeping a SQLite path alive for local dev
means maintaining two SQL dialects (placeholders, `GROUP_CONCAT` vs
`string_agg`, FTS5 vs `tsvector`) across ~25 queries, which is a standing bug
source. Single dialect is the better trade, and it is a real change to a stated
project value — flagged here rather than buried.

---

## Task 1 — Postgres schema

**Files:** Create `supabase/schema.sql`

Translate `scripts/schema.sql` twice, once per schema. Dialect differences that
actually bite:

| SQLite | Postgres |
|---|---|
| `INTEGER PRIMARY KEY` | `bigint generated always as identity primary key` |
| `datetime('now')` | `now()` |
| `GROUP_CONCAT(DISTINCT d)` | `string_agg(DISTINCT d, ',')` |
| `features_fts` FTS5 + 3 triggers | generated `tsvector` column + GIN index |
| `features_fts MATCH ?` | `search_vector @@ websearch_to_tsquery('english', $1)` |
| `?` | `$1`, `$2`, … |

The FTS5 virtual table and its three sync triggers disappear entirely, replaced
by one generated column — Postgres keeps it current with no trigger to get
wrong:

```sql
search_vector tsvector generated always as (
  to_tsvector('english',
    coalesce(name,'') || ' ' || coalesce(description,'') || ' ' || coalesce(evidence,''))
) stored
```

**Verify:** `psql "$DATABASE_URL" -f supabase/schema.sql` runs clean twice in a
row (every statement is `IF NOT EXISTS` or `OR REPLACE`).

---

## Task 2 — Migration script

**Files:** Create `scripts/publish.py`

Reads both SQLite files and upserts into the matching Postgres schema. Must be
**idempotent and re-runnable** — it is the command that gets run after every
future crawl, not a one-shot.

Order matters, because of foreign keys: `sites` → `pages` → `canonical_features`
→ `features` → `feature_links` → `annotations`.

Identity columns need care: SQLite ids are preserved so `feature_links` and
`annotations` keep pointing at the right rows, which means inserting explicit
ids and then resetting each sequence:

```sql
SELECT setval(pg_get_serial_sequence('catalog.features','id'),
              COALESCE((SELECT MAX(id) FROM catalog.features), 1));
```

Skip it and the next insert collides on a primary key that is already taken.

**Verify:** row counts match per table, per schema:

```
catalog  sites 7    pages 24   features 361  annotations 317
pdp      sites 13   pages 13   features 417  annotations 357
```

---

## Task 3 — Images to WebP and Storage

**Files:** Create `scripts/to_webp.py` (done), `scripts/upload_plates.py`

Convert preserving pixel dimensions (see the warning above), then upload to a
public bucket `plates`, keyed by the path already stored in the database with
`data/screenshots/` stripped and `.png` → `.webp`:

```
data/screenshots/pdp/arrae.com/foo.png  ->  plates/pdp/arrae.com/foo.webp
```

The app then builds URLs as
`${SUPABASE_URL}/storage/v1/object/public/plates/${key}`, so
`web/app/api/shot/route.ts` is deleted rather than ported — the CDN serves the
bytes directly and the route would only add a hop.

**Verify:** every `screenshot_path` and `crop_path` in both schemas resolves to
an object that exists in the bucket. A missing plate renders as a broken image
with no error, so this check is the only thing that catches it.

---

## Task 4 — The data layer

**Files:**
- Create `web/lib/pg.ts`
- Rewrite `web/lib/db.ts`, `web/lib/pdp-db.ts`
- Modify `web/package.json` (add `postgres`)

Vercel functions are short-lived and numerous, so the connection string must be
the **transaction pooler** (port 6543), and `postgres.js` needs
`prepare: false` against pgbouncer in transaction mode — prepared statements do
not survive a pooled connection being handed to someone else.

```ts
import postgres from "postgres";
export const sql = postgres(process.env.DATABASE_URL!, {
  prepare: false,          // required: pgbouncer transaction mode
  max: 1,                  // one socket per serverless invocation
  idle_timeout: 20,
});
```

Every exported function becomes `async`. The `plain()` null-prototype re-wrap
that `node:sqlite` forced is no longer needed — `postgres.js` returns real
objects — but the type exports stay identical so no component's props change.

---

## Task 5 — Pages become async

**Files (10 that call data functions):**

| File | Calls |
|---|---|
| `web/app/page.tsx` | `getStats`, `getSites`, `getCategories`, `getPrevalence` |
| `web/app/features/page.tsx` | `getFeatures`, `getCategories`, `getSites` |
| `web/app/screens/page.tsx` | `getPages` |
| `web/app/screens/[id]/page.tsx` | `getPage`, `getAnnotations`, `cleanPlate` |
| `web/app/compare/page.tsx` | `getSites`, `getFeatures` |
| `web/app/gaps/page.tsx` | `getGaps`, `getFeaturesByCanonical`, `getSites` |
| `web/app/search/page.tsx` | `search` |
| `web/app/sites/[domain]/page.tsx` | `getSite`, `getFeatures`, `getPages`, `getCategories` |
| `web/app/pdp/page.tsx` | `pdpSites`, `pdpStats`, `pdpCategories` |
| `web/app/pdp/matrix/page.tsx` | `pdpMatrix`, `pdpDomains` |
| `web/app/pdp/[domain]/page.tsx` | `pdpSite`, `pdpCircled`, `pdpUncircled`, `pdpCategories` |

`viewer.tsx`, `plate.tsx` and `feature-rows.tsx` import **types only** — type
imports are erased at compile time, so those three files do not change.

`web/app/capture/page.tsx` and `web/app/api/capture/route.ts` drive a pipeline
that cannot run on Vercel. Gate them behind `CATALOG_READONLY` rather than
deleting them, so the local workflow survives.

---

## Task 6 — Repository and deploy

This directory is **not a git repository yet**. Before the first commit, the
`.gitignore` has to exclude the things that must never reach GitHub:

```
.venv/
node_modules/
.next/
data/            # 695 MB of PNG + 300 MB of WebP
db/*.db
firecrawl/       # vendored upstream, and firecrawl/.env holds secrets
*.log
.env*.local
```

`firecrawl/.env` in particular is a real secret file sitting in the tree today.

Vercel project settings: **Root Directory `web`**, and three environment
variables — `DATABASE_URL` (transaction pooler, port 6543),
`NEXT_PUBLIC_SUPABASE_URL`, `CATALOG_READONLY=1`.

**Verify before calling it done:**

1. `/` reads 7 sites / 361 features / 24 pages / 317 pinned — the same numbers
   the local catalog has printed all along
2. `/pdp` reads 13 sites / 417 features / 310 circled
3. No PDP-Lab domain appears on `/`, `/features`, `/screens`, `/compare`,
   `/gaps` or `/search`
4. A plate and its circles render on `/pdp/drinkag1.com`, with circle ① still on
   "$49 billed every 30 days" — proof the WebP conversion preserved geometry
5. `/search` returns results, proving the FTS5 → `tsvector` port works
