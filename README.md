# Website Feature Catalog

Scrape websites with **self-hosted Firecrawl**, extract their product features,
and accumulate them in a **SQLite** database that gets more useful over time.

Everything here is free: no Firecrawl API key, no LLM API key.

```
  URL ──► Firecrawl (local Docker, :3002) ──► markdown on disk
                                                    │
                                          Claude reads + extracts
                                                    │
                                                    ▼
                                      db/features.db  (SQLite)
```

> **Running it day to day?** See [REQUIREMENTS.md](REQUIREMENTS.md) —
> start/stop, and the exact procedure for adding a new website.
> Start everything with `.\start.ps1`.

## Layout

| Path | What it is |
|---|---|
| `firecrawl/` | Cloned Firecrawl repo + Docker stack (git-ignored) |
| `db/features.db` | The catalog — the thing that accumulates value |
| `data/markdown/<domain>/*.md` | Raw scraped markdown, one file per page |
| `data/raw/*.json` | Extracted features, staged before insert |
| `scripts/` | Pipeline (see below) |

## Scripts

| Script | Purpose |
|---|---|
| `schema.sql` | Tables, views, FTS5 index |
| `db.py` | Shared helpers (upsert site/page/feature) |
| `firecrawl_client.py` | Stdlib HTTP client for Firecrawl (v2, falls back to v1) |
| `scrape.py` | URL → markdown file + `pages` row |
| `add_features.py` | features JSON → `features` rows |
| `query.py` | Reporting: summary, search, prevalence, compare |

## Running Firecrawl

```bash
cd firecrawl
docker compose up -d api playwright-service redis rabbitmq nuq-postgres
docker compose ps                 # health
docker compose logs -f api        # tail
docker compose stop               # free the RAM when done
```

FoundationDB services are intentionally **not** started — the default queue is
NuQ Postgres. Only the API is exposed, on `localhost:3002`, unauthenticated;
keep it on a trusted network.

## Daily use

```bash
# 1. scrape
python scripts/scrape.py https://stripe.com/pricing --name Stripe --wait 2000

# 2. Claude reads data/markdown/stripe.com/pricing.md and writes
#    data/raw/stripe.json, then:
python scripts/add_features.py data/raw/stripe.json

# 3. query
python scripts/query.py --summary
python scripts/query.py --site stripe.com
python scripts/query.py --search "single sign on"
python scripts/query.py --prevalence
python scripts/query.py --compare stripe.com adyen.com
```

## Schema notes

- `sites` — one row per domain (`stripe.com`), the canonical key.
- `pages` — one per scraped URL, with `content_hash` so unchanged re-scrapes
  can be skipped.
- `features` — unique per `(site_id, name)`, carries `evidence` (a verbatim
  quote) so every claim is traceable back to the page.
- `canonical_features` + `feature_links` — collapse "SSO" / "SAML login" /
  "Single Sign-On" into one comparable concept, which is what makes
  cross-site comparison work.
- `features_fts` — FTS5 full-text search over name/description/evidence.

## Known limits

- Self-hosted Firecrawl has **no stealth proxy**, so aggressively bot-protected
  sites (hard Cloudflare) may fail. `--wait 3000` helps with JS-heavy pages.
- Firecrawl's own `/extract` and `json` formats need an LLM key. We don't use
  them — extraction happens in-conversation instead.
- The stack idles at roughly 2–4 GB RAM. `docker compose stop` when finished.

## Gotchas found during setup

**RabbitMQ healthcheck races on first boot.** Its healthcheck is aggressive
(5s interval, 3 retries, 5s start period), so on a cold start compose can mark
it unhealthy and refuse to start `api`:

```
dependency failed to start: container firecrawl-rabbitmq-1 is unhealthy
```

Not fatal. RabbitMQ becomes healthy seconds later — just run the API again:

```bash
docker compose up -d api
```

**Windows console encoding.** The scripts call `sys.stdout.reconfigure(utf-8)`
because scraped titles contain characters cp1252 cannot print, which otherwise
crashes with `UnicodeEncodeError`.

**Markdown noise.** Marketing pages are dominated by repeated image links —
some feature pages run to 45% image lines. `clean_md.py` strips images, empty
links, hard-break backslashes and repeated nav, cutting roughly 50% of tokens
before extraction.

## Current contents

Seven pickleball paddle brands. All prices captured from US storefronts in USD.

| Site | Features | Pages | Pinned |
|---|---|---|---|
| joola.com | 84 | 5 | 62 |
| selkirk.com | 71 | 3 | 67 |
| luzzpickleball.com | 69 | 3 | 67 |
| crbnpickleball.com | 51 | 4 | 50 |
| gammasports.com | 29 | 3 | 23 |
| paddletek.com | 29 | 3 | 26 |
| us.sixzeropickleball.com | 28 | 3 | 23 |
| **Total** | **361** | **24** | **318** |

The gap between features and pinned is mostly deliberate: features found only in
a site map are recorded at `confidence` 0.7 and never circled, because there is
no rendered text to circle.

**luzz was recaptured in USD on 2026-09-12.** Its first capture was routed to
a different Shopify market and priced in another currency. When that market
changed, every price-bearing needle stopped matching and the circled count fell
from 63 to 53 overnight - which reads exactly like a code regression and was
not one. Every site in the catalogue is now priced in USD.

**Six Zero is keyed on its US subdomain.** `www.sixzeropickleball.com` serves the
Australian market in AUD; `us.sixzeropickleball.com` is the USD storefront. The
same paddle is $225 AUD on one and $180 USD on the other, so the two are not
interchangeable.

If a site is walled by a bot challenge, `annotate.py` now prints `BLOCKED`
rather than a confident `0/N`.

Only three canonical features are shared by all seven paddle brands — Feature
Benefit Blocks, Product Reviews and Product Specifications Table. That floor is
derived from the data rather than assumed, and it tightened sharply as brands
were added.

Idle RAM measured: **~3.4 GB** across the five containers (the API is the bulk).

## Visual annotation (Playwright + crawl4ai)

Second toolchain, installed in `.venv` (kept out of the global Python):
**playwright 1.62**, **crawl4ai 0.9.2**, **pillow**, plus `playwright-stealth`.

```bash
uv venv .venv && VIRTUAL_ENV=.venv uv pip install playwright crawl4ai pillow
.venv/Scripts/python -m playwright install chromium
```

### Circle features on a screenshot

```bash
.venv/Scripts/python scripts/annotate.py --site luzzpickleball.com
.venv/Scripts/python scripts/annotate.py --url URL --style box
```

How it works: each feature's stored `evidence` quote is searched for in the live
DOM, the **smallest visible element** containing it wins, and a red ellipse plus
a numbered badge is injected as an overlay before a full-page screenshot. Output:

- `data/screenshots/<domain>/<page>.png` - whole page, every feature circled
- `data/screenshots/<domain>/<page>/NN-<feature>.png` - close-up per feature
- `annotations` table - x/y/w/h, matched text and match method per feature

### Second crawler

```bash
.venv/Scripts/python scripts/c4a_scrape.py URL --locale en-GB --screenshot
```

Writes `<page>-c4a.md` so it never overwrites Firecrawl's output. Worth running
when Firecrawl misses something: Firecrawl uses `onlyMainContent`, which strips
nav/header/footer, so crawl4ai found this site's faceted mega-menu that
Firecrawl never saw (1431 words vs 225 on the same page).

### Annotation gotchas solved

| Problem | Fix |
|---|---|
| Markers invisible | Theme ships `div:empty{display:none}`; markers now carry a zero-width space and `!important` styles |
| Circles wrapped whole sections | Two-pass search rejects ancestors over ~520k px², so the circle hugs the real element |
| Prices didn't match | The storefront serves a different market than the capture did. Re-scrape and rewrite the evidence — `--locale` only helps for sites that localise by `Accept-Language`, and luzz is not one of them |
| Page dimmed grey | Email-capture modal; Escape + backdrop removal before capture |
| Collapsed copy unmatchable | `<details>` forced open and `aria-expanded=false` clicked first |
| `UnicodeEncodeError` / PIL bomb warning | UTF-8 stdout shim; `Image.MAX_IMAGE_PIXELS = None` |

## Web UI (Next.js)

```bash
cd web
npm install          # first time only
npm run dev          # http://localhost:3100
```

No database driver to compile: it reads the catalog through **`node:sqlite`**,
built into Node 22+, so there is no `better-sqlite3` native build on Windows.
The app is read-only — it never writes to `features.db`.

| Route | What it shows |
|---|---|
| `/` | Totals, site cards, category chips, screen thumbnails |
| `/features` | Every feature; filter by site, category, ★ differentiators |
| `/screens` | All captured pages |
| `/screens/[id]` | **Interactive viewer** — screenshot with live hotspots |
| `/compare` | Canonical-feature matrix across sites |
| `/search` | FTS5 search over name, description and evidence |
| `/api/shot?p=` | Serves screenshots, restricted to `data/screenshots` |

### The viewer

Rather than shipping only the burned-in circles, `annotate.py` now also saves a
**clean plate** (`<page>-clean.png`), captured before overlays are injected. The
viewer draws circles itself from the `annotations` x/y/w/h, so you can:

- toggle **clean plate ↔ burned-in circles**
- toggle overlays off entirely
- hover a circle to highlight its row, or a row to highlight its circle
- **click** either one to *lock* a spotlight on that feature
- see `loose` matches as dashed, since those hit an oversized ancestor

**Hover vs click are deliberately different colours.** Hover is the same signal
red as the burned-in circles. A click locks the feature in **cyan** (`--lock`),
dims every other hotspot to 0.18, darkens the rest of the page, and shows the
feature name plus its evidence quote. Red is already the annotation colour, so
reusing it for selection would be ambiguous; cyan never is. The page-dimming
scrim is a single `box-shadow: 0 0 0 9999px` on the locked element — `.plate`
clips it, so one element gives a spotlight with no extra DOM. Click again or
press <kbd>Esc</kbd> to clear.

Coordinates are stored in CSS pixels and screenshots are captured at
`device_scale_factor=2`, so the viewer divides natural image dimensions by 2 and
positions every hotspot in percentages — correct at any window size.

### Gotchas solved here too

| Problem | Fix |
|---|---|
| `Only plain objects can be passed to Client Components` | `node:sqlite` returns **null-prototype** rows; the data layer re-wraps each row with `{...row}` |
| `Cannot find module './873.js'` | `next build` ran while `next dev` was live — both write `.next`. Never run them together |
| Circles never appeared | The plate is usually cached and complete before hydration, so `onLoad` never fires; measure in `useEffect` when `img.complete` |
| Cart drawer opened, capture started mid-page | Popup dismissal was clicking generic buttons. It now **removes** overlays and never clicks page controls |
| A confident `0/19 circled` sent me debugging the wrong thing twice | It was a **Cloudflare bot challenge** — a real page, a real screenshot, every needle missing. `is_challenged()` now detects the wall and prints `BLOCKED` instead of a silent zero. Repeated automated hits on one host will trigger it; space runs out |
| Evidence quotes matched nothing | Composite quotes joining separate DOM nodes with invented separators (`-`, `...`, `\|`, `/`) match no single text run. **Evidence must be one contiguous fragment as it appears in the DOM.** A Playwright probe that tests each needle against the live page finds this in seconds |
| A whole review platform was invisible | Firecrawl's markdown showed no reviews on JOOLA, so the first gap analysis reported "no reviews at all". Wrong — Bazaarvoice injects **350 reviews at 4.4 stars** client-side, after the scrape window. **Markdown absence is not evidence of absence**; verify every negative finding in a rendered browser before publishing it |

## Gap analysis (`/gaps`)

`/gaps` scores one site against named rivals on the **canonical slug**, never on
the raw feature name — so JOOLA's "paddle selector quiz" and Selkirk's "Paddle
Fit Assistant" are correctly counted as the same capability. Without that
mapping the comparison would be string matching, and string matching would call
every one of these a gap.

The page has three parts:

- **Missing** — a rival ships it, the subject does not. Ranked by severity,
  then by how many rivals have it.
- **Shipped, but weaker** — the subject has the capability but executes it worse.
  These are hand-written judgements kept in `IMPROVE` in the page file, beside
  the query rather than inside it, because severity is a reading and not data.
- **Where the subject is ahead** — capabilities no rival has.

Coverage is bounded by what was crawled: absence means *not found on the crawled
pages*, not *does not exist*. A feature buried three clicks deep is still a real
finding, but the fix is surfacing it, not building it.
