"""Open every route in a real browser and report what actually renders.

    python scripts/browser_check.py
    python scripts/browser_check.py --base http://localhost:3100

HTTP 200 is not evidence that a page works. It does not tell you whether the
plates loaded from Storage, whether a client component threw after hydration,
or whether an annotation overlay landed on the right pixels. This opens each
route in Chromium, records console errors and failed network requests, counts
the images that actually decoded, and saves a screenshot to look at.

Written for the post-migration check: the two failure modes that matter here are
a plate URL that 404s (renders as a blank box, no error in the server log) and
an overlay whose geometry moved (renders fine, points at the wrong words).
"""
from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db as dbmod

from playwright.sync_api import sync_playwright

OUT = dbmod.ROOT / "data" / "browser-check"

ROUTES = [
    ("/", "overview"),
    ("/features", "features"),
    ("/screens", "screens"),
    ("/screens/15", "screen-joola-pdp"),
    ("/compare", "compare"),
    ("/gaps", "gaps"),
    ("/search?q=warranty", "search"),
    ("/capture", "capture-readonly"),
    ("/pdp", "pdp-index"),
    ("/pdp/matrix", "pdp-matrix"),
    ("/pdp/drinkag1.com", "pdp-ag1"),
    ("/pdp/jolieskinco.com", "pdp-jolie-botwall"),
    ("/sites/joola.com", "site-joola"),
]

# Noise that is not a real failure.
#
# "_rsc=" deserves a word: Next prefetches every <Link> in the nav, then aborts
# those requests once the page settles or the user navigates. They show up as
# ERR_ABORTED on every single route and mean nothing — treating them as failures
# makes the checker cry wolf on a perfectly healthy site.
IGNORE = ("favicon", "Download the React DevTools",
          "Extra attributes from the server", "_rsc=")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:3100")
    ap.add_argument("--timeout", type=int, default=60_000)
    a = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    problems = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        for route, name in ROUTES:
            errors: list[str] = []
            failed: list[str] = []
            page.on("console", lambda m, e=errors:
                    e.append(m.text) if m.type == "error" else None)
            page.on("requestfailed", lambda r, f=failed:
                    f.append(f"{r.url[:90]} {r.failure}"))

            try:
                resp = page.goto(a.base + route, wait_until="networkidle",
                                 timeout=a.timeout)
                status = resp.status if resp else 0
            except Exception as e:
                print(f"  !! {route:<28} navigation failed: {str(e)[:70]}")
                problems += 1
                continue

            # how many <img> actually decoded, and how many are broken
            imgs = page.evaluate("""() => {
                const a = [...document.images];
                return { total: a.length,
                         ok: a.filter(i => i.complete && i.naturalWidth > 0).length,
                         broken: a.filter(i => i.complete && i.naturalWidth === 0)
                                  .map(i => i.src.slice(0, 100)) };
            }""")
            overlays = page.locator(".hot").count()
            text_len = len(page.inner_text("body"))

            shot = OUT / f"{name}.png"
            page.screenshot(path=str(shot), full_page=False)

            errs = [e for e in errors if not any(k in e for k in IGNORE)]
            fails = [f for f in failed if not any(k in f for k in IGNORE)]
            bad = status != 200 or imgs["broken"] or errs or fails
            problems += 1 if bad else 0

            flag = "!!" if bad else "ok"
            print(f"  {flag} {route:<28} {status}  text={text_len:>6}  "
                  f"img {imgs['ok']}/{imgs['total']}  overlays={overlays}")
            for b in imgs["broken"][:3]:
                print(f"       broken image: {b}")
            for e in errs[:3]:
                print(f"       console error: {e[:100]}")
            for f in fails[:3]:
                print(f"       request failed: {f}")

            page.remove_listener("console", lambda *_: None) if False else None

        browser.close()

    print(f"\n  screenshots -> {OUT}")
    print(f"  {'ALL ROUTES CLEAN' if problems == 0 else f'{problems} route(s) with problems'}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
