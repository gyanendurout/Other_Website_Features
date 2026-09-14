"""Scrape URLs with self-hosted Firecrawl, save markdown, record in SQLite.

    python scripts/scrape.py https://stripe.com --name Stripe --type homepage
    python scripts/scrape.py URL1 URL2 URL3 --wait 2000
"""
from __future__ import annotations

import sys
if hasattr(sys.stdout, "reconfigure"):      # Windows console is cp1252
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

import clean_md
import db
import firecrawl_client as fc

# Pages most likely to describe product features
PAGE_TYPE_HINTS = {
    "pdp": ("/products/",),                       # ecommerce product detail
    "collection": ("/collections/", "/category/", "/shop/"),
    "pricing": ("pricing", "plans", "price"),
    "features": ("features", "product", "platform", "solutions", "capabilities"),
    "docs": ("docs", "documentation", "developer", "api"),
    "changelog": ("changelog", "whats-new", "releases", "updates"),
}


def guess_page_type(url: str) -> str:
    path = (urlparse(url).path or "/").lower()
    if path in ("", "/"):
        return "homepage"
    for kind, needles in PAGE_TYPE_HINTS.items():
        if any(n in path for n in needles):
            return kind
    return "other"


def markdown_path_for(url: str) -> Path:
    domain = db.domain_of(url)
    slug = db.slugify(urlparse(url).path.strip("/")) or "index"
    return db.MARKDOWN_DIR / domain / f"{slug[:80]}.md"


def scrape_one(con, url: str, site_name: str | None, page_type: str | None,
               wait_ms: int) -> dict:
    site_id = db.upsert_site(con, url, name=site_name)
    try:
        data = fc.scrape(url, wait_ms=wait_ms)
    except Exception as e:
        db.upsert_page(con, site_id, url, scrape_status="failed", error=str(e)[:500],
                       page_type=page_type or guess_page_type(url))
        return {"url": url, "status": "failed", "error": str(e)[:200]}

    md = clean_md.clean(data.get("markdown") or "")
    meta = data.get("metadata") or {}
    out = markdown_path_for(url)
    out.parent.mkdir(parents=True, exist_ok=True)
    header = f"<!-- source: {url} -->\n<!-- title: {meta.get('title','')} -->\n\n"
    out.write_text(header + md, encoding="utf-8")

    page_id = db.upsert_page(
        con, site_id, url,
        title=meta.get("title"),
        page_type=page_type or guess_page_type(url),
        markdown_path=str(out.relative_to(db.ROOT)).replace("\\", "/"),
        content_hash=db.sha256(md),
        word_count=len(md.split()),
        http_status=meta.get("statusCode"),
        scrape_status="ok",
    )
    return {"url": url, "status": "ok", "page_id": page_id,
            "title": meta.get("title"), "words": len(md.split()),
            "path": str(out.relative_to(db.ROOT)).replace("\\", "/")}


def main() -> int:
    ap = argparse.ArgumentParser(description="Scrape URLs into the feature catalog")
    ap.add_argument("urls", nargs="+")
    ap.add_argument("--name", help="Site display name, e.g. Stripe")
    ap.add_argument("--type", dest="page_type", help="Override page type")
    ap.add_argument("--wait", type=int, default=0, help="ms to wait for JS render")
    args = ap.parse_args()

    if not fc.is_up():
        print(f"ERROR: Firecrawl not reachable at {fc.BASE_URL}", file=sys.stderr)
        return 2

    con = db.connect()
    failures = 0
    for url in args.urls:
        r = scrape_one(con, url, args.name, args.page_type, args.wait)
        if r["status"] == "ok":
            print(f"  OK   {r['words']:>6} words  {r['path']}  <- {url}")
        else:
            failures += 1
            print(f"  FAIL {url}\n       {r['error']}", file=sys.stderr)
    con.close()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
