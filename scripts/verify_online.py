"""Check the published Postgres copy against the local SQLite catalogs.

    python scripts/verify_online.py

Compares the headline numbers the site renders, per schema, against the same
numbers computed locally. A migration that loses or duplicates rows still
produces a site that loads and looks fine, so "it renders" is not evidence of
anything — these counts are.

Also asserts the two schemas stay disjoint: the whole isolation guarantee is
that no PDP-Lab domain appears in the paddle catalog's numbers. luzzpickleball
is in both by design and is the one expected overlap.
"""
from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db as dbmod

import psycopg

ENV = dbmod.ROOT / ".env.local"
PAIRS = [("catalog", dbmod.ROOT / "db" / "features.db"),
         ("pdp", dbmod.ROOT / "db" / "pdp.db")]

COUNTS = {
    "sites":              "SELECT COUNT(*) FROM {p}sites",
    "pages (ok)":         "SELECT COUNT(*) FROM {p}pages WHERE scrape_status='ok'",
    "features":           "SELECT COUNT(*) FROM {p}features",
    "canonical":          "SELECT COUNT(*) FROM {p}canonical_features",
    "feature_links":      "SELECT COUNT(*) FROM {p}feature_links",
    "annotations":        "SELECT COUNT(*) FROM {p}annotations",
    "circled":            "SELECT COUNT(*) FROM {p}annotations WHERE match_method <> 'failed'",
    "differentiators":    "SELECT COUNT(*) FROM {p}features WHERE is_differentiator = 1",
}


def env() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def main() -> int:
    e = env()
    conn = psycopg.connect(host=e["PGHOST"], port=5432, dbname=e["PGDATABASE"],
                           user=e["PGUSER"], password=e["PGPASSWORD"],
                           connect_timeout=20)
    bad = 0
    for schema, sqlite_path in PAIRS:
        print(f"\n  {schema}   (vs {sqlite_path.name})")
        print("  " + "-" * 58)
        lite = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
        for label, tmpl in COUNTS.items():
            local = lite.execute(tmpl.format(p="")).fetchone()[0]
            remote = conn.execute(tmpl.format(p=f"{schema}.")).fetchone()[0]
            ok = local == remote
            bad += 0 if ok else 1
            mark = "ok " if ok else "!! "
            print(f"  {mark}{label:<20} local {local:>5}   postgres {remote:>5}")
        lite.close()

    # isolation: the paddle catalog must not contain PDP-Lab-only domains
    print("\n  isolation")
    print("  " + "-" * 58)
    cat = {r[0] for r in conn.execute("SELECT domain FROM catalog.sites")}
    pdp = {r[0] for r in conn.execute("SELECT domain FROM pdp.sites")}
    overlap = cat & pdp
    expected = {"luzzpickleball.com"}
    if overlap == expected:
        print(f"  ok  overlap is exactly {sorted(overlap)} — by design")
    else:
        bad += 1
        print(f"  !!  overlap {sorted(overlap)}, expected {sorted(expected)}")

    # full-text search has to actually work after the FTS5 -> tsvector port
    print("\n  full-text search")
    print("  " + "-" * 58)
    for schema, term in (("catalog", "warranty"), ("pdp", "subscription")):
        n = conn.execute(
            f"SELECT COUNT(*) FROM {schema}.features "
            f"WHERE search_vector @@ websearch_to_tsquery('english', %s)", (term,)
        ).fetchone()[0]
        ok = n > 0
        bad += 0 if ok else 1
        print(f"  {'ok ' if ok else '!! '}{schema}.features MATCH '{term}' -> {n} rows")

    # every plate path should now be a storage key, never a local path
    print("\n  storage keys")
    print("  " + "-" * 58)
    for schema in ("catalog", "pdp"):
        stale = conn.execute(
            f"SELECT COUNT(*) FROM {schema}.annotations "
            f"WHERE screenshot_path LIKE 'data/%' OR screenshot_path LIKE '%.png'"
        ).fetchone()[0]
        bad += 0 if stale == 0 else 1
        print(f"  {'ok ' if stale == 0 else '!! '}{schema}: {stale} un-rewritten path(s)")

    conn.close()
    print(f"\n  {'ALL CHECKS PASSED' if bad == 0 else f'{bad} CHECK(S) FAILED'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
