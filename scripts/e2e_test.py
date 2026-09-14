"""End-to-end interaction tests against the running site.

    python scripts/e2e_test.py
    python scripts/e2e_test.py --base http://localhost:3100 --headed

Goes past "the page returned 200". Drives the real interactions a person uses —
clicking a circle, toggling the plate, filtering features, pressing Escape — and
asserts what should have happened actually did. Also checks the two things this
migration could plausibly have broken and that no status code would reveal:

  * plates really come from Supabase Storage and really decode
  * the read-only deployment really refuses writes

Every check prints PASS or FAIL with what it expected, so a failure says what is
wrong rather than that something is.
"""
from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db as dbmod

from playwright.sync_api import sync_playwright, expect

OUT = dbmod.ROOT / "data" / "e2e"

PASS = FAIL = 0
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> bool:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"    PASS  {label}")
    else:
        FAIL += 1
        FAILURES.append(f"{label} — {detail}")
        print(f"    FAIL  {label}" + (f"   [{detail}]" if detail else ""))
    return ok


def group(name: str) -> None:
    print(f"\n  {name}\n  " + "-" * 66)


def run(base: str, headed: bool) -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        console_errors: list[str] = []
        page.on("console", lambda m: console_errors.append(m.text)
                if m.type == "error" else None)

        # ---------------------------------------------------------------- A
        group("A · navigation works from the nav bar")
        for label, expect_path in [
            ("Features", "/features"), ("Screens", "/screens"),
            ("Compare", "/compare"), ("Gaps", "/gaps"),
            ("Search", "/search"), ("PDP Lab", "/pdp"),
        ]:
            # Always start from a known page: these are Next <Link>s doing
            # client-side navigation, so go_back() after a click that did not
            # navigate leaves the tab somewhere unhelpful.
            page.goto(base + "/", wait_until="domcontentloaded", timeout=60000)
            page.click(f"nav a[href='{expect_path}']")
            try:
                # client-side nav: the URL changes without a document load event
                page.wait_for_url(f"**{expect_path}", timeout=20000)
                ok, detail = True, ""
            except Exception:
                ok, detail = False, f"landed on {page.url}"
            check(f"nav '{label}' -> {expect_path}", ok, detail)

        page.goto(base + "/pdp", wait_until="domcontentloaded")
        active = page.get_attribute("nav a[href='/pdp']", "data-active")
        check("active nav item is marked on /pdp", active == "true", f"data-active={active}")

        # ---------------------------------------------------------------- B
        group("B · plates are served from Supabase Storage and decode")
        storage_responses: list[tuple[int, str]] = []
        page.on("response", lambda r: storage_responses.append((r.status, r.url))
                if "supabase.co/storage" in r.url else None)

        page.goto(base + "/pdp/drinkag1.com", wait_until="networkidle", timeout=90000)
        check("at least one Storage request was made", len(storage_responses) > 0,
              f"{len(storage_responses)} requests")
        bad = [u for s, u in storage_responses if s != 200]
        check("every Storage response is 200", not bad, f"{len(bad)} non-200")

        dims = page.evaluate("""() => { const i = document.querySelector('.plate img');
            return i ? {w: i.naturalWidth, h: i.naturalHeight, src: i.src} : null; }""")
        check("plate image decoded", bool(dims and dims["w"] > 0),
              str(dims))
        check("plate is served at DPR 1 (1440 css px wide)",
              bool(dims) and dims["w"] == 1440, f"naturalWidth={dims and dims['w']}")
        check("plate src points at the Storage bucket",
              bool(dims) and "/storage/v1/object/public/plates/" in dims["src"],
              dims and dims["src"][:70])

        # ---------------------------------------------------------------- C
        group("C · PDP plate interactions")
        hots = page.locator(".hot")
        n_hot = hots.count()
        check("overlays rendered", n_hot == 37, f"{n_hot} overlays, expected 37")

        rail = page.locator(".pdp-expl")
        check("rail rows match overlays", rail.count() == n_hot,
              f"{rail.count()} rail rows vs {n_hot} overlays")

        # How many overlays are unreachable because another overlay sits on top
        # of their centre? Circles are absolutely positioned from annotation
        # boxes, and two features found on adjacent nav links overlap. A real
        # mouse click then lands on the wrong one. Reported, not asserted --
        # it predates this migration and is a design question, not a regression.
        covered = page.evaluate("""() => {
            const hots = [...document.querySelectorAll('.hot')];
            let blocked = [];
            for (const h of hots) {
                const r = h.getBoundingClientRect();
                if (r.width === 0) continue;
                const el = document.elementFromPoint(r.x + r.width/2, r.y + r.height/2);
                if (el && el !== h && !h.contains(el) && el.classList.contains('hot'))
                    blocked.push(h.getAttribute('title'));
            }
            return blocked;
        }""")
        print(f"    NOTE  {len(covered)} of {n_hot} circles are overlapped by another "
              f"circle at their centre")
        for t in covered[:4]:
            print(f"          - {t}")

        # Drive the handler directly rather than with a synthetic mouse click:
        # this asserts the component's state machine, not the browser's hit
        # testing, which the overlap above would otherwise decide for us.
        hots.nth(4).dispatch_event("click")
        page.wait_for_timeout(400)
        check("clicked circle becomes locked",
              hots.nth(4).get_attribute("data-locked") == "true")
        check("plate enters spotlight mode",
              page.get_attribute(".plate", "data-locked") == "true")
        check("matching rail row is locked",
              rail.nth(4).get_attribute("data-locked") == "true")
        check("toolbar shows the locked feature name",
              (page.inner_text(".toolbar") or "").strip() != "")

        # Escape clears it
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        check("Escape clears the spotlight",
              page.get_attribute(".plate", "data-locked") != "true")

        # clicking the same circle twice toggles off
        hots.nth(2).dispatch_event("click"); page.wait_for_timeout(250)
        hots.nth(2).dispatch_event("click"); page.wait_for_timeout(250)
        check("clicking a locked circle unlocks it",
              hots.nth(2).get_attribute("data-locked") != "true")

        # hovering a rail row highlights its circle
        rail.nth(7).hover()
        page.wait_for_timeout(250)
        check("hovering a rail row activates its circle",
              hots.nth(7).get_attribute("data-active") == "true")

        # plate toggle actually swaps the image
        before = page.get_attribute(".plate img", "src")
        page.click(".toolbar button:has-text('Clean plate')")
        page.wait_for_timeout(700)
        after = page.get_attribute(".plate img", "src")
        check("plate toggle swaps the image src", before != after,
              f"unchanged: {before[-40:] if before else None}")
        check("the other plate is the -clean twin",
              "-clean.webp" in (before or "") or "-clean.webp" in (after or ""),
              f"{before[-30:] if before else ''} / {after[-30:] if after else ''}")
        newdims = page.evaluate(
            "() => { const i=document.querySelector('.plate img'); return i.naturalWidth; }")
        check("swapped plate also decodes", newdims > 0, f"naturalWidth={newdims}")

        # overlays can be hidden
        page.click(".toolbar button:has-text('Overlays')")
        page.wait_for_timeout(400)
        check("overlays toggle off", page.locator(".hot").count() == 0,
              f"{page.locator('.hot').count()} still visible")
        page.click(".toolbar button:has-text('Overlays')")
        page.wait_for_timeout(400)
        check("overlays toggle back on", page.locator(".hot").count() == n_hot)

        page.screenshot(path=str(OUT / "pdp-interactions.png"))

        # ---------------------------------------------------------------- D
        group("D · the bot-walled PDP explains itself instead of breaking")
        page.goto(base + "/pdp/jolieskinco.com", wait_until="networkidle", timeout=90000)
        body = page.inner_text("body")
        check("no plate is shown", page.locator(".plate").count() == 0)
        check("the bot-challenge explanation is rendered",
              "bot challenge" in body.lower(), "explanation missing")
        check("its features are still listed",
              page.locator(".pdp-expl").count() > 20,
              f"{page.locator('.pdp-expl').count()} rows")

        # ---------------------------------------------------------------- E
        group("E · screens viewer (the paddle catalog's plate)")
        page.goto(base + "/screens/15", wait_until="networkidle", timeout=90000)
        n2 = page.locator(".hot").count()
        check("screens viewer renders overlays", n2 > 0, f"{n2}")
        sdims = page.evaluate("""() => { const i=document.querySelector('.plate img');
            return i ? {w:i.naturalWidth, src:i.src} : null; }""")
        check("its plate decodes from Storage",
              bool(sdims) and sdims["w"] > 0 and "supabase.co" in sdims["src"],
              str(sdims)[:80])
        page.locator(".hot").first.dispatch_event("click")
        page.wait_for_timeout(400)
        check("clicking a circle locks it here too",
              page.get_attribute(".plate", "data-locked") == "true")

        # ---------------------------------------------------------------- F
        group("F · features page filtering")
        page.goto(base + "/features", wait_until="domcontentloaded", timeout=90000)
        total = page.locator(".frow").count()
        check("all features listed", total == 361, f"{total} rows, expected 361")

        page.goto(base + "/features?cat=social-proof", wait_until="domcontentloaded")
        filtered = page.locator(".frow").count()
        check("category filter narrows the list", 0 < filtered < total,
              f"{filtered} of {total}")

        page.goto(base + "/features?site=joola.com", wait_until="domcontentloaded")
        jo = page.locator(".frow").count()
        check("site filter returns joola's 84 features", jo == 84, f"{jo}")

        page.goto(base + "/features?diff=1", wait_until="domcontentloaded")
        diffs = page.locator(".frow").count()
        check("differentiator filter returns 131", diffs == 131, f"{diffs}")

        # ---------------------------------------------------------------- G
        group("G · search (FTS5 -> tsvector port)")
        page.goto(base + "/search", wait_until="domcontentloaded")
        page.fill("input[name='q']", "warranty")
        page.press("input[name='q']", "Enter")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(500)
        res = page.locator(".frow").count()
        check("typed search returns results", res > 0, f"{res} rows")
        check("search term is reflected in the url", "warranty" in page.url, page.url)

        page.goto(base + "/search?q=zzzznotathing", wait_until="domcontentloaded")
        check("a nonsense query returns no rows, without erroring",
              page.locator(".frow").count() == 0)

        # ---------------------------------------------------------------- H
        group("H · every site detail page loads")
        paddle = ["joola.com", "selkirk.com", "luzzpickleball.com", "crbnpickleball.com",
                  "gammasports.com", "paddletek.com", "us.sixzeropickleball.com"]
        for d in paddle:
            r = page.goto(f"{base}/sites/{d}", wait_until="domcontentloaded", timeout=60000)
            check(f"/sites/{d}", r.status == 200 and page.locator(".frow").count() > 0,
                  f"status={r.status}")

        pdp_domains = ["arrae.com", "drinkag1.com", "jolieskinco.com", "seed.com",
                       "cymbiotika.com", "myobvi.com", "snitch.com", "luzzpickleball.com",
                       "thesusoutdoors.com", "mvmt.com", "purecycles.com",
                       "supergoop.com", "aachho.com"]
        for d in pdp_domains:
            r = page.goto(f"{base}/pdp/{d}", wait_until="domcontentloaded", timeout=60000)
            has = page.locator(".pdp-expl").count()
            check(f"/pdp/{d}", r.status == 200 and has > 0, f"status={r.status} rows={has}")

        # ---------------------------------------------------------------- I
        group("I · matrix and the comparison pages")
        page.goto(base + "/pdp/matrix", wait_until="domcontentloaded", timeout=90000)
        rows = page.locator("table.pdp-matrix tbody tr").count()
        cols = page.locator("table.pdp-matrix thead th").count()
        check("matrix has a row per canonical feature plus category headers",
              rows > 132, f"{rows} rows")
        check("matrix has 13 domain columns + name + n", cols == 15, f"{cols} columns")
        on = page.locator("td.pdp-cell[data-on='true']").count()
        # 416, not the 417 feature_links rows: the matrix is keyed on
        # (canonical, site), and seed.com maps two distinct features onto
        # "Infographic Slide", which correctly collapses to a single cell.
        check("matrix marks 416 distinct site/feature pairs", on == 416,
              f"{on} filled cells")

        page.goto(base + "/compare", wait_until="domcontentloaded", timeout=90000)
        check("compare page renders content", len(page.inner_text("body")) > 2000)
        page.goto(base + "/gaps", wait_until="domcontentloaded", timeout=90000)
        check("gaps page renders content", len(page.inner_text("body")) > 2000)

        # ---------------------------------------------------------------- J
        group("J · read-only deployment refuses writes")
        r = page.request.post(base + "/api/capture",
                              data={"url": "https://example.com", "name": "Test"})
        check("POST /api/capture is refused", r.status == 403, f"status={r.status}")
        body_txt = r.text()
        check("refusal explains itself", "read-only" in body_txt.lower(), body_txt[:90])
        rg = page.request.get(base + "/api/capture")
        check("GET /api/capture still works (job list)", rg.status == 200, f"{rg.status}")

        page.goto(base + "/capture", wait_until="domcontentloaded")
        check("capture page shows the read-only panel, not a form",
              page.locator("form").count() == 0
              and "read-only" in page.inner_text("body").lower())

        # Console errors are judged on everything up to here. Section K below
        # visits missing pages deliberately, and a 404 it asked for is not a
        # fault in the site.
        errors_before_404_tests = list(console_errors)

        # ---------------------------------------------------------------- K
        group("K · unknown routes 404 rather than crash")
        r = page.goto(base + "/pdp/not-a-real-site.com", wait_until="domcontentloaded")
        check("/pdp/<unknown> returns 404", r.status == 404, f"status={r.status}")
        r = page.goto(base + "/sites/not-a-real-site.com", wait_until="domcontentloaded")
        check("/sites/<unknown> returns 404", r.status == 404, f"status={r.status}")

        # ---------------------------------------------------------------- L
        group("L · phone width (400px) stays usable")
        mob = ctx.new_page()
        mob.set_viewport_size({"width": 400, "height": 840})
        for route in ["/", "/pdp", "/pdp/drinkag1.com", "/features"]:
            mob.goto(base + route, wait_until="domcontentloaded", timeout=90000)
            overflow = mob.evaluate(
                "() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
            check(f"{route} has no horizontal overflow at 400px",
                  overflow <= 2, f"overflows by {overflow}px")
        mob.goto(base + "/pdp/drinkag1.com", wait_until="networkidle", timeout=90000)
        mob.screenshot(path=str(OUT / "mobile-pdp.png"))
        mob.close()

        # ---------------------------------------------------------------- M
        group("M · no console errors across the whole run")
        real = [e for e in errors_before_404_tests
                if not any(k in e for k in ("favicon", "DevTools", "_rsc"))]
        check("browser console stayed clean (excluding the deliberate 404s)",
              not real, f"{len(real)} errors, first: {real[0][:90] if real else ''}")
        if real:
            for e in real[:5]:
                print(f"          {e[:110]}")

        browser.close()

    print("\n  " + "=" * 68)
    print(f"  {PASS} passed, {FAIL} failed")
    if FAILURES:
        print("\n  failures:")
        for f in FAILURES:
            print(f"    - {f}")
    print(f"  screenshots -> {OUT}")
    return 1 if FAIL else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:3100")
    ap.add_argument("--headed", action="store_true")
    a = ap.parse_args()
    return run(a.base, a.headed)


if __name__ == "__main__":
    raise SystemExit(main())
