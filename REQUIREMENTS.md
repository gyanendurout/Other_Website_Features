# Feature Catalog — Operating Requirements

What this system is, what it needs to run, and the exact procedure for adding a
new website. Read `README.md` for architecture; read this for **operation**.

---

## 1. Starting and stopping

```powershell
.\start.ps1              # everything: Docker, Firecrawl, Next.js
.\start.ps1 -Rebuild     # also wipe web/.next (after a dependency change)
.\start.ps1 -NoWeb       # containers only (batch crawling, no UI)
.\stop.ps1               # stop everything, keep data
.\stop.ps1 -Volumes      # also drop Firecrawl's queue/cache volumes
```

`start.ps1` is idempotent — running it twice is safe. It will:

1. Start Docker Desktop if it isn't running (waits up to 3 min)
2. Bring up the five Firecrawl containers, **retrying once** — the first
   launch of a freshly-created RabbitMQ container exits 1 and aborts the `api`
   container with it. An immediate re-run succeeds every time
3. Wait for the API on `:3002`
4. Kill any stale listener on `:3100`, then start `next dev`
5. Print container states and the catalog totals

**When the user says "start the server", run `.\start.ps1`.** Nothing else is
needed — no manual `docker compose`, no separate `npm run dev`.

| Service | URL | Notes |
|---|---|---|
| Web UI | http://localhost:3100 | Next.js dev |
| Firecrawl API | http://localhost:3002 | `/` is the liveness path; `/test` 404s. ~60s to boot |
| Catalog DB | `db/features.db` | SQLite on the host, never in a container |
| Dev log | `data/web-dev.log` | where `next dev` output goes |

Idle cost: ~3.4 GB RAM across the five containers. **No API keys. No spend.**

---

## 2. What must exist

| Requirement | Check | If missing |
|---|---|---|
| Docker Desktop | `docker info` | `start.ps1` launches it |
| Node 22+ | `node -v` | needed for `node:sqlite` (no native build) |
| Python venv | `.venv\Scripts\python.exe` | `uv venv && uv pip install -r requirements` |
| Playwright browser | `playwright install chromium` | needed only for annotation |
| `web/node_modules` | — | `start.ps1` runs `npm install` once |

Deliberately **not** required: a Firecrawl API key, an LLM API key, FoundationDB.
Feature extraction is a reading step performed in conversation, not an LLM call.

---

## 3. Adding a new website — the full procedure

> Give a URL and this runs end to end. Steps 1–2 are automated, step 3 is a
> reading task, steps 4–5 are automated.

### Step 1 — Capture

Either paste the URL at http://localhost:3100/capture, or:

```powershell
.venv\Scripts\python.exe scripts\capture.py --url https://example.com --name "Example"
```

This maps the site, picks one page of each type it can find (homepage,
collection, pricing, features, PDP), scrapes each to clean markdown in
`data/markdown/<domain>/`, and stops at `awaiting_extraction`.

**Check what it picked before continuing.** Auto-discovery sorts by URL path
length, which is a decent heuristic and an occasionally bad one — on JOOLA it
chose a *logo towel* as the representative product page. If the pages are not
representative, scrape better ones by hand:

```powershell
.venv\Scripts\python.exe scripts\scrape.py https://example.com/the/right/page --wait 3000
```

To find candidate URLs when `map` doesn't surface them, scrape a collection page
and grep its links:

```bash
grep -oE '/products/[a-z0-9-]+' data/markdown/<domain>/<collection>.md | sort -u
```

### Step 2 — Second engine on the homepage

Firecrawl's `onlyMainContent: true` strips nav, header and footer. That hides
mega-menus, which are often where a site's whole information architecture lives.
Always run crawl4ai on the homepage as well:

```powershell
.venv\Scripts\python.exe scripts\c4a_scrape.py https://example.com/
```

Writes `<page>-c4a.md` so the two engines never clobber each other. On JOOLA this
was the difference between seeing a flat header and seeing a three-axis
(Shape / Series / Skill Level) paddle menu.

### Step 3 — Extract features (reading task)

Read every markdown file for the site and write `data/raw/<domain>.json`:

```json
{
  "site": {
    "url": "https://example.com/",
    "name": "Example",
    "vertical": "...",
    "business_model": "...",
    "tagline": "...",
    "description": "which pages were analyzed and what the brand is",
    "notes": "platform, observed third-party apps, what was NOT found"
  },
  "features": [
    {
      "name": "Short specific label",
      "canonical": "Existing Canonical Name",
      "category": "conversion",
      "tier": "free",
      "is_differentiator": 1,
      "confidence": 1.0,
      "description": "What it does and why it matters.",
      "evidence": "one contiguous run of text exactly as it appears",
      "source_url": "https://example.com/the-page-it-came-from"
    }
  ]
}
```

**Rules that are not optional:**

- **`evidence` must be ONE contiguous string as rendered in the DOM.** Do not
  join separate elements with `-`, `...`, `|` or `/`. A composite quote reads
  well and matches nothing, and the annotator will correctly report it as
  `failed`. This single mistake caused a 7/19 match rate on JOOLA.
- **Reuse `canonical` names that already exist.** Run
  `python scripts/query.py --canonical` first. Cross-site comparison happens on
  the canonical slug — a new synonym silently becomes a fake gap.
- **`source_url` must match a scraped page URL exactly**, or the feature won't
  link to a page and can never be circled.
- **Never invent evidence from a URL slug.** If something is only visible in the
  site map, say so in the description and set `confidence` ≤ 0.7. It will not be
  circled, and that is correct.

Then load it:

```powershell
.venv\Scripts\python.exe scripts\add_features.py data\raw\<domain>.json
```

### Step 4 — Annotate

```powershell
.venv\Scripts\python.exe scripts\annotate.py --site <domain> --wait 3000
```

Optional flags: `--style box`, `--locale <tag>`.

**`--locale` is not optional when the site localises.** It must match the market
the evidence was captured from, or every price-bearing needle misses and the run
silently loses features — re-annotating luzz without it dropped 63 circled to 53
in one go, which looks exactly like a code regression and is not one.

Every site in this catalogue is now captured from its US storefront in USD, so
no `--locale` flag is needed for any of them. Pass one only if you add a site
whose evidence was captured from a non-US market.

**A sharp drop in the circled count usually means the market moved, not that the
code broke.** luzz was originally captured in another currency; when its
storefront switched, every price-bearing needle stopped matching and the count
fell from 63 to 53. The fix was a re-scrape and an evidence rewrite, not a code
change. Check what the live page actually renders before touching `annotate.py`:

```powershell
.venv\Scripts\python.exe scriptserify.py <url> --find "<a price string>"
```

Reads output honestly:

| Output | Meaning |
|---|---|
| `29/37 circled` | good — chase the rest via the failure list below |
| `BLOCKED` | a bot wall was served. **Stop and wait.** Do not retry in a loop |
| `0/N circled` | evidence strings are wrong, or the page changed |

**Always compare the two plates afterwards.** `annotate.py` writes
`<page>-clean.png` and then `<page>.png`, and the crops are cut from the second
one. Anything that lands between them — a popup on a timer is the usual
culprit — ruins the annotated plate while leaving the clean plate perfect, so
the run still reports a healthy `8/12 circled`. Two cheap checks catch it:

```powershell
# annotated much smaller than clean == content did not paint
Get-ChildItem data\screenshots\<domain>\*.png | Select-Object Name, Length
```

and a brightness comparison — a dimmer behind a modal darkens the whole plate
(Six Zero's PDP went from mean 120 to 30 this way). If the annotated plate is
blank below the fold, the modal locked body scrolling: a full-page capture of a
scroll-locked page paints only the visible region.


List what failed and why:

```powershell
.venv\Scripts\python.exe scripts\query.py --failed <domain>
```

### Step 5 — Verify before publishing any conclusion

**Markdown absence is not evidence of absence.** Anything injected client-side —
review platforms, chat widgets, personalisation — is invisible to the scrape.
JOOLA appeared to have zero reviews; it actually has **350 reviews at 4.4
stars** via Bazaarvoice, injected after the scrape window.

Before claiming a site *lacks* something, check it in a real browser:

```powershell
.venv\Scripts\python.exe scripts\verify.py https://example.com/product-page
```


### Ground truth is the screenshot, not a probe

Three separate scripted browser probes reported that JOOLA had no reviews and
no Q&A. All three were wrong. The PDP runs a full Bazaarvoice stack - 350
reviews, verified-purchaser badges, star filters, secondary Quality/Value
scores, public brand replies, review syndication, and a community Q&A. It was
only found by opening the captured PNG and reading it.

Lazy-mounted widgets can defeat `innerText` checks even after networkidle and
several scroll passes. `verify.py` is a fast first pass; when a negative
finding actually matters, **crop the plate and look at it**:

```python
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
im = Image.open("data/screenshots/<domain>/<page>-clean.png")
w, h = im.size
im.crop((0, int(h*0.52), w, int(h*0.60))).save("C:/tmp/look.png")
```

Then update `web/app/gaps/page.tsx` if this site is the comparison subject.

---

## 4. Politeness and rate limits

These are live third-party websites.

- **Space runs out.** Roughly 15 automated hits in 30 minutes triggered
  Cloudflare on joola.com and blocked everything for a while.
- **Never retry a `BLOCKED` result in a loop.** Wait, then try once.
- **Never click page controls.** `JS_DISMISS` removes overlays instead of
  clicking them, and `JS_EXPAND` refuses anything matching
  `add to cart|buy|checkout|subscribe|pay` or sitting inside a `<form>`. This
  exists because an early version added a paddle to a live store's cart.
- Prefer `--wait 3000`+ over hammering with short waits.

---

## 5. Common failures

| Symptom | Cause | Fix |
|---|---|---|
| `dependency failed to start: rabbitmq exited (1)` | first launch of a newly created container; cause not established | `start.ps1` retries once, which is reliable |
| `dependency failed to start: rabbitmq is unhealthy` | upstream allows ~20s; RabbitMQ needs ~40s | fixed by `firecrawl/docker-compose.override.yaml` (`start_period: 120s`) |
| `0/N circled`, screenshots ~44 KB and identical | bot challenge page | wait; `is_challenged()` now reports `BLOCKED` |
| Feature matched the wrong element | needle too generic | make `evidence` longer and more distinctive |
| Screenshot is of a **different page** | `JS_EXPAND` clicked a nav link that navigated | fixed: it now refuses `<a href>` that leaves the page, and the run aborts with `DRIFTED` rather than saving a wrong plate |
| A whole feature area is missing from the analysis | it mounts late in JS | `verify.py` is a first pass only — crop and read the plate |
| Annotated plate blank below the fold, clean plate fine | a timed popup locked body scrolling after the clean shot | fixed: the overlay killer is installed via `add_init_script` and re-runs on a MutationObserver + 1s interval, so it also kills popups that arrive mid-capture |
| A popup survives the killer | it has `z-index: auto` | fixed: `parseInt("auto")` is `NaN`, so any rule gated on `z > 100` silently failed. A fixed full-viewport layer is now removed on position alone — this is how GAMMA's `<iframe id=attentive_creative>` got through |
| A cookie bar sits across the plate | too short to trip the modal size test | fixed: consent bars are matched by name (`cookie|consent|gdpr`) and removed when fixed and over half the viewport wide. Deliberately name-gated — a fixed top bar is otherwise a real feature, e.g. GAMMA's free-shipping announcement |
| A circle spans a third of the page | the needle matched a whole page section | fixed: the fallback match pass is capped at 2,000,000 px². The feature now reports as failed, which is honest — rewrite its `evidence` to something tighter |
| A feature has coordinates but no crop, `x` is negative | matched a marquee clone parked off-canvas | fixed: `findSmallest` skips elements whose document-space rect is entirely negative |
| `Cannot find module './873.js'` | `next build` ran while `next dev` was live | `.\start.ps1 -Rebuild` |
| `Only plain objects can be passed to Client Components` | `node:sqlite` returns null-prototype rows | already handled by `plain()` in `web/lib/db.ts` |
| Prices differ between markdown and screenshot | site localises by `Accept-Language` | pass `--locale` to `annotate.py` |
| PowerShell: `NativeCommandError` on a docker call | PS 5.1 wraps native stderr as errors | never `2>&1` a native exe; test `$LASTEXITCODE` |

---

## 6. Where things live

```
db/features.db              the catalog (SQLite; the durable asset)
data/raw/<domain>.json      extracted features, re-importable
data/markdown/<domain>/     scraped markdown, per engine
data/screenshots/<domain>/  full-page plates + per-feature crops
scripts/                    capture, scrape, extract, annotate, query, stats
web/                        Next.js UI on :3100
firecrawl/                  vendored self-hosted Firecrawl + .env
start.ps1 / stop.ps1        the whole local stack
```

Everything in `data/` and `db/` is reproducible from `data/raw/*.json` plus a
re-scrape, except the screenshots.

---

## 7. The PDP Lab — a second, isolated catalog

`/pdp` in the web UI is a separate catalog of **single product-detail pages**
from unrelated verticals (supplements, skincare, apparel, footwear, watches,
bicycles). It exists to answer "what features does a modern PDP have" without
touching the paddle catalog.

### Why it is a second database

`web/lib/db.ts` queries `sites`, `features`, `pages` and `annotations` with **no
site filter** — `getStats()` is literally `COUNT(*) FROM sites`. Loading PDP
sites into `db/features.db` would silently change the totals on Overview,
Features, Screens, Compare, Gaps and Search, and would pollute the canonical
taxonomy that `/gaps` compares on. So the PDP Lab is a second SQLite file built
from the same `scripts/schema.sql`.

It also removes three collisions for free: `luzzpickleball.com` appears in both
catalogs, and a shared file would have collided on `sites.domain`,
`data/markdown/<domain>/` and `data/screenshots/<domain>/`.

### Running the pipeline against it

Three environment variables repoint every script. Set all three or none:

```powershell
$env:CATALOG_DB='db/pdp.db'
$env:CATALOG_MARKDOWN='data/pdp/markdown'
$env:CATALOG_SHOTS='data/screenshots/pdp'
```

| Variable | Default | PDP Lab |
|---|---|---|
| `CATALOG_DB` | `db/features.db` | `db/pdp.db` |
| `CATALOG_MARKDOWN` | `data/markdown` | `data/pdp/markdown` |
| `CATALOG_SHOTS` | `data/screenshots` | `data/screenshots/pdp` |

Relative values resolve against the project root, so they work from any cwd.
Screenshots deliberately stay **inside** `data/screenshots/` because
`web/app/api/shot/route.ts` refuses to serve anything outside it.

**Every script honours them** — `scrape.py`, `c4a_scrape.py`, `add_features.py`,
`annotate.py`, `query.py`, `stats.py`, `verify.py`. Forgetting one writes PDP
data into the paddle catalog, which is the one genuinely destructive mistake
available here. `stats.py` with no env set must always print 7 sites / 361
features; if it does not, something leaked.

### Procedure for adding a PDP

The five steps of §3 apply unchanged, with two differences:

1. **Always pass `--type pdp`.** Half these URLs have no `/products/` segment
   (`seed.com/daily-multivitamin`, `mvmt.com/...28000532.html`) and would
   otherwise be typed `other`.
2. **Always run both engines on the same URL.** Firecrawl's
   `onlyMainContent: true` strips the announcement bar, sticky add-to-cart,
   badge rail and footer — on a PDP that is a third of the features. crawl4ai
   also rescues pages Firecrawl times out on: it took Jolie from 38 words to
   4,188, and was the only engine that got Seed and MVMT at all.

### Two extra scripts, both worth running every time

```powershell
.venv\Scripts\python.exe scripts\pdp_validate.py        # before loading
.venv\Scripts\python.exe scripts\plate_check.py         # after annotating
```

`pdp_validate.py` catches the evidence mistakes that otherwise surface an hour
later as `0/N circled`: composite quotes stitched with `-` `|` `/` `...`,
needles absent from both captures, `source_url` values that match no scraped
page, canonical names missing from `data/pdp/canonical.md`, and needles too
short to be distinctive.

`plate_check.py` compares each annotated plate against its `-clean` twin on
**height and mean luminance**, which is the only way to catch the failure where
a popup lands between the two shots and the run still reports a healthy circled
count.

### The canonical vocabulary is written first

`data/pdp/canonical.md` is the shared list of canonical feature names, and it is
authored **before** extraction, not after. Comparison keys on the canonical
slug, so independent extractors inventing "Subscribe & Save", "Subscription
discount" and "Sub & Save" produce three one-site features and a fake gap. An
extractor that finds something genuinely new proposes an addition rather than
bending it into a poor fit.
