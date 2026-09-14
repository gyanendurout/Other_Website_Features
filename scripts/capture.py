"""Run a capture job: discover representative pages, scrape them, record progress.

Queued by the web UI, then run detached:

    python scripts/capture.py --job 7
    python scripts/capture.py --url https://example.com --name Example

Feature extraction is deliberately NOT done here - it needs a reader. Jobs stop
at `awaiting_extraction` so the markdown is ready to be turned into features.
"""
from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import traceback
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db
import firecrawl_client as fc
import scrape as fc_scrape

# how many pages of each kind to take when auto-discovering
QUOTA = {"homepage": 1, "pricing": 1, "features": 1, "collection": 1, "pdp": 1}
MAX_PAGES = 5


# ---------------------------------------------------------------- job state

def set_job(con, job_id: int, **fields) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    con.execute(
        f"UPDATE jobs SET {cols}, updated_at = datetime('now') WHERE id = ?",
        (*fields.values(), job_id),
    )
    con.commit()


def create_job(con, url: str, name: str | None) -> int:
    cur = con.execute(
        "INSERT INTO jobs (url, domain, site_name) VALUES (?, ?, ?)",
        (url, db.domain_of(url), name),
    )
    con.commit()
    return int(cur.lastrowid)


# ---------------------------------------------------------------- discovery

def discover(url: str) -> list[str]:
    """Pick a small, representative set of pages for the site."""
    root = f"{urlparse(url).scheme}://{urlparse(url).netloc}/"
    chosen: list[str] = [url]
    taken = {fc_scrape.guess_page_type(url): 1}

    try:
        links = fc.map_site(root, limit=400)
    except Exception:
        links = []

    # keep same-host links only
    host = urlparse(root).netloc.lower()
    links = [l for l in links if urlparse(l).netloc.lower() == host]

    # shortest URL of each type first - usually the canonical hub page
    links.sort(key=lambda l: (len(urlparse(l).path), l))

    for link in links:
        if len(chosen) >= MAX_PAGES:
            break
        kind = fc_scrape.guess_page_type(link)
        if kind == "other":
            continue
        if taken.get(kind, 0) >= QUOTA.get(kind, 0):
            continue
        if link.rstrip("/") in {c.rstrip("/") for c in chosen}:
            continue
        chosen.append(link)
        taken[kind] = taken.get(kind, 0) + 1

    return chosen


# ---------------------------------------------------------------- runner

def run(con, job_id: int, wait_ms: int) -> int:
    job = con.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        print(f"no job {job_id}", file=sys.stderr)
        return 2

    url, name = job["url"], job["site_name"]
    try:
        if not fc.is_up():
            raise RuntimeError(f"Firecrawl not reachable at {fc.BASE_URL}")

        set_job(con, job_id, stage="discovering", message="looking for key pages")
        pages = discover(url)
        set_job(con, job_id, stage="scraping", pages_found=len(pages),
                message=f"scraping {len(pages)} pages")

        ok = bad = 0
        for page_url in pages:
            r = fc_scrape.scrape_one(con, page_url, name, None, wait_ms)
            if r["status"] == "ok":
                ok += 1
                print(f"  OK   {r['words']:>6} words  {page_url}")
            else:
                bad += 1
                print(f"  FAIL {page_url}: {r['error']}", file=sys.stderr)
            set_job(con, job_id, pages_scraped=ok, pages_failed=bad)

        if ok == 0:
            raise RuntimeError("every page failed to scrape")

        set_job(con, job_id, stage="awaiting_extraction", status="ok",
                message=f"{ok} pages scraped - ready for feature extraction",
                finished_at=None)
        set_job(con, job_id, finished_at=None)
        print(f"job {job_id}: {ok} scraped, {bad} failed -> awaiting_extraction")
        return 0

    except Exception as e:
        traceback.print_exc()
        set_job(con, job_id, stage="failed", status="failed",
                message=str(e)[:400])
        return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", type=int, help="run an existing queued job")
    ap.add_argument("--url", help="create and run a new job")
    ap.add_argument("--name", help="site display name")
    ap.add_argument("--wait", type=int, default=2500)
    a = ap.parse_args()

    con = db.connect()
    if a.job:
        job_id = a.job
    elif a.url:
        job_id = create_job(con, a.url, a.name)
        print(f"created job {job_id}")
    else:
        ap.error("pass --job or --url")
    code = run(con, job_id, a.wait)
    con.close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
