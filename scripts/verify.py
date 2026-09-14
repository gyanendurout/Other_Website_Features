"""Check what a page ACTUALLY renders, before claiming a site lacks something.

    python scripts/verify.py https://example.com/product
    python scripts/verify.py https://example.com/product --find "trade-in,klarna"

Why this exists: Firecrawl returns the server HTML converted to markdown. Any
feature injected by JavaScript after that snapshot is invisible to it. JOOLA
looked like it had no reviews at all; it actually has 350 reviews at 4.4 stars
via Bazaarvoice, injected client-side. A whole "missing feature" finding was
wrong because of it.

Absence in markdown is not absence on the page. Verify negatives here first.
"""
from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):      # Windows console is cp1252
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Third-party platforms worth knowing about, because each one implies a whole
# feature that a markdown scrape will usually miss.
VENDORS = {
    "reviews": ["bazaarvoice", "judge.me", "judgeme", "yotpo", "okendo",
                "stamped", "loox", "trustpilot", "reviews.io", "powerreviews",
                "feefo", "junip"],
    "loyalty / referral": ["smile.io", "loyaltylion", "yotpo-loyalty",
                           "swell", "referralcandy", "friendbuy", "talkable"],
    "email / sms": ["klaviyo", "attentive", "postscript", "omnisend",
                    "mailchimp", "privy", "drip"],
    "search / merch": ["algolia", "searchspring", "klevu", "nosto",
                       "constructor", "boost", "rebuy"],
    "support / chat": ["gorgias", "zendesk", "intercom", "tidio", "gladly",
                       "drift", "helpscout"],
    "quiz / finder": ["octaneai", "visually.io", "prehook", "lantern"],
    "subscriptions": ["recharge", "skio", "loop", "bold"],
    "payments / bnpl": ["klarna", "afterpay", "affirm", "sezzle", "shop-pay"],
    "size / fit": ["kiwisizing", "truefit", "fitanalytics", "3dlook"],
    "ugc / social": ["foursixty", "pixlee", "bazaarvoice-ugc", "tagshop"],
    "accessibility": ["accessibe", "userway", "equalweb", "audioeye"],
}

SIGNALS = {
    "star rating": ["out of 5", "stars", "★"],
    "review count": ["reviews", "review)"],
    "Q&A": ["ask a question", "answer this question", "1 answer",
            "questions &", "answered"],
    "verified reviews": ["verified purchaser", "verified buyer",
                         "verified purchase"],
    "review filtering": ["clear all", "5 stars", "sort by"],
    "merchant replies": ["response from", "team joola", "reply from"],
    "secondary ratings": ["quality of product", "value of product",
                          "fit:", "overall rating"],
    "review syndication": ["originally posted on"],
    "write a review": ["write a review", "review this product"],
    "trial / guarantee": ["day trial", "day guarantee", "money back",
                          "risk free", "play test", "demo program"],
    "free shipping": ["free shipping", "free delivery"],
    "loyalty": ["rewards", "points", "earn ", "cashback", "store credit"],
    "back in stock": ["notify me", "back in stock", "email when available"],
    "financing": ["klarna", "afterpay", "affirm", "4 interest-free",
                  "pay in 4"],
    "size guide": ["size chart", "size guide", "fit guide"],
    "breadcrumb": ["home /", "home>"],
    "wishlist": ["wishlist", "save for later", "add to favourites",
                 "add to favorites"],
    "comparison": ["compare", "vs."],
}

CHALLENGE = ("verify you are human", "connection needs to be verified",
             "checking your browser", "just a moment", "attention required")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--find", help="extra comma-separated strings to look for")
    ap.add_argument("--wait", type=int, default=6000)
    ap.add_argument("--passes", type=int, default=3,
                    help="scroll passes; late-mounting review widgets need >1")
    ap.add_argument("--json", action="store_true", help="machine-readable")
    a = ap.parse_args()

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        try:
            page.goto(a.url, wait_until="domcontentloaded", timeout=90_000)
        except Exception as exc:
            print(f"could not load {a.url}: {exc}")
            return 2
        try:
            page.wait_for_load_state("networkidle", timeout=25_000)
        except Exception:
            pass
        page.wait_for_timeout(a.wait)

        # Review and Q&A platforms mount late, in stages, and only once their
        # container is in view. A single scroll pass was not enough: JOOLA's
        # Bazaarvoice block stayed invisible to two scripted probes and was
        # only caught by reading the screenshot. Scroll repeatedly, waiting in
        # between, and give the page a real chance to finish.
        SCROLL = """async () => {
            await new Promise(res => {
              let y = 0;
              const step = () => {
                window.scrollBy(0, 700); y += 700;
                if (y < document.body.scrollHeight && y < 90000)
                    setTimeout(step, 70);
                else { setTimeout(res, 1500); }
              };
              step();
            });
        }"""
        for _ in range(a.passes):
            page.evaluate(SCROLL)
            page.wait_for_timeout(3000)
        page.evaluate("() => window.scrollTo(0, 0)")
        page.wait_for_timeout(1000)

        # Widgets often live in an iframe; the top document's innerText will
        # not contain a word of them.
        frame_text = []
        for fr in page.frames:
            try:
                frame_text.append(fr.inner_text("body"))
            except Exception:
                continue

        data = page.evaluate("""() => ({
            title: document.title || "",
            text: (document.body.innerText || ""),
            scripts: [...document.querySelectorAll("script[src]")]
                       .map(s => s.src).join(" "),
            html: document.documentElement.outerHTML.slice(0, 400000),
            ld: [...document.querySelectorAll('script[type="application/ld+json"]')]
                  .map(s => s.textContent || "").join("\\n"),
            iframes: [...document.querySelectorAll("iframe")]
                       .map(f => f.src || "").join(" "),
        })""")
        browser.close()

    # every frame's text counts as "on the page"
    text = "\n".join([data["text"], *frame_text])
    low = (data["title"] + " " + text[:2000]).lower()
    if any(m in low for m in CHALLENGE) or len(text.strip()) < 400:
        print("BLOCKED - a bot challenge was served, not the page.")
        print("Wait before retrying; do not loop.")
        return 3

    # Match vendors against loaded script and iframe URLs only. Scanning the
    # whole DOM produced five "review platforms" on a site that uses one - a
    # cookie-consent banner lists every vendor it knows about, and that text
    # is not evidence the vendor is in use.
    blob = (data["scripts"] + " " + data["iframes"]).lower()
    body = text.lower()

    found_vendors = {
        kind: [v for v in vs if v in blob]
        for kind, vs in VENDORS.items()
    }
    found_vendors = {k: v for k, v in found_vendors.items() if v}
    found_signals = {
        name: [s for s in ss if s in body]
        for name, ss in SIGNALS.items()
    }
    found_signals = {k: v for k, v in found_signals.items() if v}

    extra = {}
    if a.find:
        for term in [t.strip() for t in a.find.split(",") if t.strip()]:
            extra[term] = term.lower() in body or term.lower() in blob

    has_agg = "aggregaterating" in data["ld"].lower()

    if a.json:
        print(json.dumps({
            "url": a.url, "title": data["title"],
            "vendors": found_vendors, "signals": found_signals,
            "aggregateRating": has_agg, "extra": extra,
            "words": len(text.split()),
        }, indent=2))
        return 0

    print(f"\n  {data['title'][:90]}")
    print(f"  {len(text.split())} words rendered\n")

    print("  third-party platforms (from loaded script/iframe URLs)")
    if found_vendors:
        for kind, vs in found_vendors.items():
            print(f"    {kind:20} {', '.join(vs)}")
    else:
        print("    (none)")

    print("\n  on-page signals")
    if found_signals:
        for name, ss in found_signals.items():
            print(f"    {name:20} {', '.join(repr(s) for s in ss[:3])}")
    else:
        print("    (none)")

    print(f"\n  JSON-LD aggregateRating: {'yes' if has_agg else 'no'}")

    if extra:
        print("\n  requested terms")
        for term, hit in extra.items():
            print(f"    {'FOUND   ' if hit else 'missing '} {term}")

    print("\n  Anything listed here is present on the rendered page even if the")
    print("  scraped markdown does not mention it. Do not report it as a gap.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
