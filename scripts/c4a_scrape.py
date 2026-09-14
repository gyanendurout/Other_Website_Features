"""Scrape with crawl4ai instead of Firecrawl, into the same catalog.

Second engine, useful when Firecrawl is down, blocked, or when a page needs
locale/geo control that the self-hosted Firecrawl stack does not expose.

    .venv/Scripts/python scripts/c4a_scrape.py https://example.com --name Example
    .venv/Scripts/python scripts/c4a_scrape.py URL --locale en-IN --screenshot
"""
from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import asyncio
import base64
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import clean_md
import db
import scrape as fc_scrape          # reuse page-type + path helpers


def _markdown_of(result) -> str:
    """crawl4ai returns either a str or a MarkdownGenerationResult."""
    md = getattr(result, "markdown", None)
    if md is None:
        return ""
    for attr in ("fit_markdown", "raw_markdown"):
        val = getattr(md, attr, None)
        if isinstance(val, str) and val.strip():
            return val
    return md if isinstance(md, str) else str(md)


async def crawl(urls: list[str], name: str | None, page_type: str | None,
                locale: str | None, wait_ms: int, want_shot: bool) -> int:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

    browser = BrowserConfig(headless=True, viewport_width=1440, viewport_height=900)
    run_kwargs = {
        "cache_mode": CacheMode.BYPASS,
        "wait_until": "domcontentloaded",
        "page_timeout": 90_000,
        "screenshot": want_shot,
    }
    if locale:
        run_kwargs["locale"] = locale
    if wait_ms:
        run_kwargs["delay_before_return_html"] = wait_ms / 1000

    con = db.connect()
    failures = 0

    async with AsyncWebCrawler(config=browser) as crawler:
        for url in urls:
            site_id = db.upsert_site(con, url, name=name)
            try:
                res = await crawler.arun(url=url, config=CrawlerRunConfig(**run_kwargs))
            except Exception as e:
                failures += 1
                db.upsert_page(con, site_id, url, scrape_status="failed",
                               error=str(e)[:500])
                print(f"  FAIL {url}\n       {e}", file=sys.stderr)
                continue

            if not getattr(res, "success", False):
                failures += 1
                err = getattr(res, "error_message", "unknown error")
                db.upsert_page(con, site_id, url, scrape_status="failed",
                               error=str(err)[:500])
                print(f"  FAIL {url}\n       {err}", file=sys.stderr)
                continue

            md = clean_md.clean(_markdown_of(res))
            base = fc_scrape.markdown_path_for(url)
            # keep engines from overwriting each other's output
            out = base.with_name(base.stem + '-c4a.md')
            out.parent.mkdir(parents=True, exist_ok=True)
            title = (getattr(res, "metadata", None) or {}).get("title", "")
            out.write_text(f"<!-- source: {url} -->\n<!-- title: {title} -->\n"
                           f"<!-- engine: crawl4ai -->\n\n" + md, encoding="utf-8")

            shot_note = ""
            if want_shot and getattr(res, "screenshot", None):
                shot_dir = db.SHOT_DIR / db.domain_of(url)
                shot_dir.mkdir(parents=True, exist_ok=True)
                shot = shot_dir / f"{out.stem}-c4a.png"
                shot.write_bytes(base64.b64decode(res.screenshot))
                shot_note = f"  +shot {shot.name}"

            db.upsert_page(
                con, site_id, url,
                title=title or None,
                page_type=page_type or fc_scrape.guess_page_type(url),
                markdown_path=str(out.relative_to(db.ROOT)).replace("\\", "/"),
                content_hash=db.sha256(md),
                word_count=len(md.split()),
                http_status=getattr(res, "status_code", None),
                scrape_status="ok",
            )
            print(f"  OK   {len(md.split()):>6} words  "
                  f"{out.relative_to(db.ROOT)}{shot_note}")
    con.close()
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Scrape into the catalog via crawl4ai")
    ap.add_argument("urls", nargs="+")
    ap.add_argument("--name")
    ap.add_argument("--type", dest="page_type")
    ap.add_argument("--locale", help="e.g. en-IN")
    ap.add_argument("--wait", type=int, default=0, help="ms before capture")
    ap.add_argument("--screenshot", action="store_true")
    a = ap.parse_args()
    return asyncio.run(crawl(a.urls, a.name, a.page_type, a.locale,
                             a.wait, a.screenshot))


if __name__ == "__main__":
    raise SystemExit(main())
