"""Push the local SQLite catalogs to Supabase Postgres.

    set DATABASE_URL=postgresql://...
    python scripts/publish.py                  # both catalogs
    python scripts/publish.py --only pdp
    python scripts/publish.py --dry-run

This is the command to run after every crawl, not a one-off migration, so it is
idempotent: re-running it updates changed rows and leaves everything else alone.

    db/features.db  ->  schema "catalog"
    db/pdp.db       ->  schema "pdp"

## Two things that will bite if changed

**Ids are carried over verbatim.** `feature_links` and `annotations` reference
features by id, so renumbering on insert would silently re-point annotations at
the wrong features -- circles would land on the right page around the wrong
words. Rows are inserted with explicit ids and each identity sequence is then
reset with setval(); skip the reset and the next insert collides with an id that
is already taken.

**Insert order follows the foreign keys**: sites -> pages -> canonical_features
-> features -> feature_links -> annotations.

Screenshot paths are rewritten to their published form as they go:
`data/screenshots/pdp/x/y.png` -> `pdp/x/y.webp`, which is the object key in the
Storage bucket. See scripts/upload_plates.py, which must run against the same
data or the site renders broken images with no error.
"""
from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import os
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db as dbmod

import psycopg

ROOT = dbmod.ROOT

CATALOGS = {
    "catalog": ROOT / "db" / "features.db",
    "pdp": ROOT / "db" / "pdp.db",
}

# table -> (columns, conflict target). Order is the foreign-key order.
TABLES: list[tuple[str, list[str], str]] = [
    ("sites", ["id", "domain", "name", "homepage_url", "vertical",
               "business_model", "tagline", "description", "first_seen_at",
               "last_scraped_at", "notes"], "id"),
    ("pages", ["id", "site_id", "url", "title", "page_type", "markdown_path",
               "content_hash", "word_count", "http_status", "scrape_status",
               "error", "scraped_at"], "id"),
    ("canonical_features", ["id", "slug", "name", "category"], "id"),
    ("features", ["id", "site_id", "page_id", "name", "category", "description",
                  "evidence", "confidence", "tier", "is_differentiator",
                  "extracted_at"], "id"),
    ("feature_links", ["feature_id", "canonical_id"], "feature_id, canonical_id"),
    ("annotations", ["id", "feature_id", "page_id", "screenshot_path",
                     "crop_path", "x", "y", "w", "h", "matched_text",
                     "match_method", "created_at"], "id"),
]

# columns holding a path that must become a Storage object key
PATH_COLUMNS = {"screenshot_path", "crop_path"}


def object_key(path: str | None) -> str | None:
    """`data/screenshots/pdp/a/b.png` -> `pdp/a/b.webp` (the Storage key)."""
    if not path:
        return None
    p = path.replace("\\", "/")
    prefix = "data/screenshots/"
    if p.startswith(prefix):
        p = p[len(prefix):]
    return p[:-4] + ".webp" if p.lower().endswith(".png") else p


def sqlite_rows(path: Path, table: str, cols: list[str]) -> list[tuple]:
    if not path.exists():
        return []
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(f"SELECT {', '.join(cols)} FROM {table}").fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        con.close()

    out = []
    for r in rows:
        vals = []
        for c in cols:
            v = r[c]
            if c in PATH_COLUMNS:
                v = object_key(v)
            vals.append(v)
        out.append(tuple(vals))
    return out


def push(cur, schema: str, table: str, cols: list[str], conflict: str,
         rows: list[tuple]) -> int:
    if not rows:
        return 0
    collist = ", ".join(f'"{c}"' for c in cols)
    placeholders = "(" + ", ".join(["%s"] * len(cols)) + ")"
    updates = ", ".join(f'"{c}" = EXCLUDED."{c}"'
                        for c in cols if c not in conflict.split(", "))

    # identity columns reject a supplied value unless OVERRIDING is stated
    overriding = "OVERRIDING SYSTEM VALUE " if "id" in cols else ""
    sql = (f'INSERT INTO {schema}.{table} ({collist}) {overriding}VALUES {placeholders} '
           f"ON CONFLICT ({conflict}) DO UPDATE SET {updates}"
           if updates else
           f'INSERT INTO {schema}.{table} ({collist}) {overriding}VALUES {placeholders} '
           f"ON CONFLICT ({conflict}) DO NOTHING")
    cur.executemany(sql, rows)
    return len(rows)


def reset_sequence(cur, schema: str, table: str) -> None:
    """Point the identity sequence past the highest id we just inserted."""
    cur.execute(
        f"SELECT setval(pg_get_serial_sequence(%s, 'id'), "
        f"COALESCE((SELECT MAX(id) FROM {schema}.{table}), 1))",
        (f"{schema}.{table}",),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Publish local catalogs to Postgres")
    ap.add_argument("--only", choices=sorted(CATALOGS), help="one schema only")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    a = ap.parse_args()

    targets = {a.only: CATALOGS[a.only]} if a.only else CATALOGS

    if a.dry_run:
        for schema, path in targets.items():
            print(f"  {schema}  <- {path.name}")
            for table, cols, _ in TABLES:
                n = len(sqlite_rows(path, table, cols))
                print(f"      {table:<20} {n:>5} rows")
        return 0

    if not a.dsn:
        print("ERROR: set DATABASE_URL (Supabase > Project Settings > Database)",
              file=sys.stderr)
        print("       use the SESSION pooler or direct connection for this script;",
              file=sys.stderr)
        print("       the transaction pooler is for the web app, not for DDL.",
              file=sys.stderr)
        return 2

    total = 0
    with psycopg.connect(a.dsn, autocommit=False) as conn:
        with conn.cursor() as cur:
            for schema, path in targets.items():
                if not path.exists():
                    print(f"  skip {schema}: {path} not found")
                    continue
                print(f"  {schema}  <- {path.name}")
                for table, cols, conflict in TABLES:
                    rows = sqlite_rows(path, table, cols)
                    n = push(cur, schema, table, cols, conflict, rows)
                    if "id" in cols:
                        reset_sequence(cur, schema, table)
                    total += n
                    print(f"      {table:<20} {n:>5} rows")
        conn.commit()

    print(f"\n  {total} rows published")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
