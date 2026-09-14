"""Apply supabase/schema.sql to a Postgres database.

    python scripts/apply_schema.py                       # uses .env.local
    python scripts/apply_schema.py --dsn "postgres://..."

Exists because this project has no `psql` on the machine, and because the schema
is one file with DO blocks and dollar-quoting that must reach the server intact
rather than being split on semicolons by something naive.

Connects on the SESSION pooler (5432), not the transaction pooler (6543): DDL
and role creation want a stable session, and `ALTER DEFAULT PRIVILEGES` is a
session-scoped statement.
"""
from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db as dbmod

import psycopg

SCHEMA = dbmod.ROOT / "supabase" / "schema.sql"
ENV = dbmod.ROOT / ".env.local"


def load_env() -> dict[str, str]:
    out: dict[str, str] = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply the Postgres schema")
    ap.add_argument("--dsn")
    ap.add_argument("--port", type=int, default=5432,
                    help="5432 session pooler (default), 6543 transaction")
    a = ap.parse_args()

    env = load_env()
    if a.dsn:
        conn_args: dict = {"conninfo": a.dsn}
    else:
        host = env.get("PGHOST") or os.environ.get("PGHOST")
        if not host:
            print("ERROR: no --dsn and no PGHOST in .env.local", file=sys.stderr)
            return 2
        conn_args = {
            "host": host,
            "port": a.port,
            "dbname": env.get("PGDATABASE", "postgres"),
            "user": env.get("PGUSER"),
            "password": env.get("PGPASSWORD"),
        }

    sql = SCHEMA.read_text(encoding="utf-8")
    print(f"  applying {SCHEMA.name} ({len(sql):,} bytes) on port {a.port}")

    # autocommit: CREATE INDEX and CREATE ROLE are happier outside an explicit
    # transaction, and a partial failure should leave what succeeded in place
    # rather than silently rolling the whole schema back.
    with psycopg.connect(**conn_args, autocommit=True, connect_timeout=20) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)          # no params -> simple query protocol
        print("  applied\n")

        for q, label in [
            ("""SELECT table_schema, COUNT(*) FROM information_schema.tables
                 WHERE table_schema IN ('catalog','pdp') AND table_type='BASE TABLE'
                 GROUP BY 1 ORDER BY 1""", "tables"),
            ("""SELECT schemaname, COUNT(*) FROM pg_indexes
                 WHERE schemaname IN ('catalog','pdp') GROUP BY 1 ORDER BY 1""", "indexes"),
            ("""SELECT table_schema, COUNT(*) FROM information_schema.views
                 WHERE table_schema IN ('catalog','pdp') GROUP BY 1 ORDER BY 1""", "views"),
        ]:
            rows = conn.execute(q).fetchall()
            print(f"  {label:<8} " + "  ".join(f"{r[0]}={r[1]}" for r in rows))

        role = conn.execute(
            "SELECT rolname, rolcanlogin FROM pg_roles WHERE rolname='catalog_read'"
        ).fetchone()
        print(f"  role     {role[0]} (login={role[1]})" if role else "  role     MISSING")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
