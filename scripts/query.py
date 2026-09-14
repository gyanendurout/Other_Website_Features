"""Read-side queries over the feature catalog.

    python scripts/query.py --summary
    python scripts/query.py --site stripe.com
    python scripts/query.py --search "single sign on"
    python scripts/query.py --prevalence
    python scripts/query.py --compare stripe.com adyen.com
"""
from __future__ import annotations

import sys
if hasattr(sys.stdout, "reconfigure"):      # Windows console is cp1252
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db


def _table(rows, cols):
    if not rows:
        print("  (nothing yet)")
        return
    widths = [max(len(str(c)), max(len(str(r[c] if r[c] is not None else "")) for r in rows))
              for c in cols]
    widths = [min(w, 60) for w in widths]
    print("  " + "  ".join(str(c).ljust(w) for c, w in zip(cols, widths)))
    print("  " + "  ".join("-" * w for w in widths))
    for r in rows:
        print("  " + "  ".join(
            str(r[c] if r[c] is not None else "")[:60].ljust(w)
            for c, w in zip(cols, widths)))


def summary(con):
    print("\nSITES IN CATALOG")
    _table(con.execute("SELECT * FROM v_site_summary ORDER BY feature_count DESC").fetchall(),
           ["domain", "name", "vertical", "feature_count", "page_count", "last_scraped_at"])
    tot = con.execute("SELECT COUNT(*) n FROM features").fetchone()["n"]
    st = con.execute("SELECT COUNT(*) n FROM sites").fetchone()["n"]
    print(f"\n  TOTAL: {tot} features across {st} sites")


def by_site(con, domain):
    print(f"\nFEATURES FOR {domain}")
    _table(con.execute(
        "SELECT feature, category, tier, is_differentiator AS key, description "
        "FROM v_features WHERE domain = ? ORDER BY category, feature", (domain,)).fetchall(),
        ["feature", "category", "tier", "key", "description"])


def search(con, term):
    print(f"\nSEARCH: {term!r}")
    _table(con.execute("""
        SELECT s.domain, f.name AS feature, f.category, f.description
        FROM features_fts x
        JOIN features f ON f.id = x.rowid
        JOIN sites s ON s.id = f.site_id
        WHERE features_fts MATCH ?
        ORDER BY rank LIMIT 50""", (term,)).fetchall(),
        ["domain", "feature", "category", "description"])


def prevalence(con):
    print("\nMOST COMMON FEATURES ACROSS SITES")
    _table(con.execute("SELECT * FROM v_feature_prevalence LIMIT 50").fetchall(),
           ["slug", "name", "category", "site_count", "sites"])


def compare(con, domains):
    print(f"\nCOMPARISON: {', '.join(domains)}")
    marks = con.execute(f"""
        SELECT c.name AS feature, s.domain
        FROM canonical_features c
        JOIN feature_links l ON l.canonical_id = c.id
        JOIN features f ON f.id = l.feature_id
        JOIN sites s ON s.id = f.site_id
        WHERE s.domain IN ({','.join('?' * len(domains))})""", domains).fetchall()
    grid = {}
    for m in marks:
        grid.setdefault(m["feature"], set()).add(m["domain"])
    if not grid:
        print("  (no canonical features linked for these sites yet)")
        return
    w = max(len(f) for f in grid)
    print("  " + "FEATURE".ljust(w) + "  " + "  ".join(d[:14].center(14) for d in domains))
    for feat in sorted(grid):
        print("  " + feat.ljust(w) + "  " +
              "  ".join(("YES" if d in grid[feat] else "-").center(14) for d in domains))


RE_SLUGGY = re.compile(r"^[a-z0-9][a-z0-9._/-]*$")


def canonical(con, term: str | None = None) -> None:
    """List the canonical taxonomy plus which sites use each entry.

    Run this BEFORE extracting a new site. Cross-site comparison keys on the
    canonical slug, so inventing a synonym for something that already exists
    quietly manufactures a fake gap.
    """
    sql = """SELECT cf.slug, cf.name, cf.category,
                    GROUP_CONCAT(DISTINCT s.domain) sites,
                    COUNT(DISTINCT s.domain) n
               FROM canonical_features cf
               LEFT JOIN feature_links fl ON fl.canonical_id = cf.id
               LEFT JOIN features f ON f.id = fl.feature_id
               LEFT JOIN sites s ON s.id = f.site_id
              {where}
              GROUP BY cf.id ORDER BY cf.category, cf.name"""
    params = ()
    if term:
        sql = sql.format(where="WHERE cf.name LIKE ? OR cf.slug LIKE ?")
        params = (f"%{term}%", f"%{term}%")
    else:
        sql = sql.format(where="")
    rows = con.execute(sql, params).fetchall()
    print(f"  {len(rows)} canonical features"
          + (f" matching {term!r}" if term else ""))
    cat = None
    for r in rows:
        if r["category"] != cat:
            cat = r["category"]
            print(f"\n  [{cat or 'uncategorised'}]")
        print(f"    {r['name'][:38]:38} {r['slug'][:32]:32} "
              f"{r['n']}x  {r['sites'] or '-'}")


def failed(con, domain: str) -> None:
    """Features that could not be circled, and the likely reason."""
    rows = con.execute(
        """SELECT f.name, f.evidence, f.confidence, a.match_method, p.url
             FROM features f
             JOIN sites s ON s.id = f.site_id
             LEFT JOIN annotations a ON a.feature_id = f.id
             LEFT JOIN pages p ON p.id = f.page_id
            WHERE s.domain = ?
              AND (a.match_method = 'failed' OR a.match_method IS NULL)
            ORDER BY p.url, f.name""", (domain,)
    ).fetchall()
    if not rows:
        print(f"  every feature on {domain} is circled")
        return
    print(f"  {len(rows)} unpinned on {domain}\n")
    for r in rows:
        ev = (r["evidence"] or "").strip()
        # the two mistakes that cause almost every failure
        if any(sep in ev for sep in (" ... ", " | ", " / ", " - ")):
            why = "composite evidence - split it into ONE contiguous run"
        elif RE_SLUGGY.match(ev):
            why = "evidence is a URL slug, not visible text"
        elif len(ev) < 8:
            why = "evidence too short to be distinctive"
        elif (r["confidence"] or 1.0) <= 0.7:
            why = "map-only feature, not expected on a page"
        else:
            why = "not found - may be client-side injected, or in an iframe"
        print(f"    {r['name'][:36]:36} {why}")
        print(f"      evidence: {ev[:80]!r}")



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--site")
    ap.add_argument("--search")
    ap.add_argument("--prevalence", action="store_true")
    ap.add_argument("--compare", nargs="+")
    ap.add_argument("--canonical", nargs="?", const="", metavar="TERM",
                    help="list the canonical taxonomy (optionally filtered)")
    ap.add_argument("--failed", metavar="DOMAIN",
                    help="features that could not be circled, and why")
    a = ap.parse_args()

    con = db.connect()
    if a.site:            by_site(con, a.site)
    elif a.search:        search(con, a.search)
    elif a.prevalence:    prevalence(con)
    elif a.compare:       compare(con, a.compare)
    elif a.canonical is not None: canonical(con, a.canonical or None)
    elif a.failed:        failed(con, a.failed)
    else:                 summary(con)
    con.close()


if __name__ == "__main__":
    main()
