"""Print a one-screen summary of what the catalog currently holds.

    python scripts/stats.py            # per-site table + totals
    python scripts/stats.py --shared   # also list features every site ships

Used by start.ps1 for its closing summary, and useful on its own to answer
"what have I actually collected?" without opening the web UI.
"""
from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):      # Windows console is cp1252
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shared", action="store_true",
                    help="list canonical features present on every site")
    ap.add_argument("--quiet", action="store_true",
                    help="one totals line only")
    a = ap.parse_args()

    if not db.DB_PATH.exists():
        print("no catalog yet - run scripts/init_db.py or a capture first")
        return 1

    con = db.connect()

    totals = con.execute(
        "SELECT (SELECT COUNT(*) FROM sites) sites,"
        "       (SELECT COUNT(*) FROM features) features,"
        "       (SELECT COUNT(*) FROM pages WHERE scrape_status='ok') pages,"
        "       (SELECT COUNT(*) FROM annotations WHERE match_method!='failed') pinned"
    ).fetchone()

    if a.quiet:
        print(f"catalog: {totals['sites']} sites | {totals['features']} features "
              f"| {totals['pages']} pages | {totals['pinned']} pinned")
        return 0

    rows = con.execute(
        """SELECT s.domain,
             (SELECT COUNT(*) FROM features f WHERE f.site_id = s.id) fc,
             (SELECT COUNT(*) FROM pages p
               WHERE p.site_id = s.id AND p.scrape_status='ok') pc,
             (SELECT COUNT(*) FROM annotations a
                JOIN features f2 ON f2.id = a.feature_id
               WHERE f2.site_id = s.id AND a.match_method != 'failed') an
           FROM sites s ORDER BY fc DESC"""
    ).fetchall()

    print(f"  {'site':24} {'features':>8} {'pages':>6} {'pinned':>7}")
    print(f"  {'-' * 24} {'-' * 8:>8} {'-' * 6:>6} {'-' * 7:>7}")
    for r in rows:
        print(f"  {r['domain']:24} {r['fc']:>8} {r['pc']:>6} {r['an']:>7}")
    print(f"  {'-' * 24} {'-' * 8:>8} {'-' * 6:>6} {'-' * 7:>7}")
    print(f"  {'TOTAL':24} {totals['features']:>8} {totals['pages']:>6} "
          f"{totals['pinned']:>7}")

    if a.shared and rows:
        n = len(rows)
        shared = con.execute(
            """SELECT cf.name, COUNT(DISTINCT s.domain) k
                 FROM canonical_features cf
                 JOIN feature_links fl ON fl.canonical_id = cf.id
                 JOIN features f ON f.id = fl.feature_id
                 JOIN sites s ON s.id = f.site_id
                GROUP BY cf.id HAVING k = ? ORDER BY cf.name""", (n,)
        ).fetchall()
        print(f"\n  shared by all {n} sites:")
        for r in shared:
            print(f"    {r['name']}")
        if not shared:
            print("    (none)")

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
