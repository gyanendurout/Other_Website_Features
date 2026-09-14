"""Upload converted plates to a Supabase Storage bucket.

    set SUPABASE_URL=https://<ref>.supabase.co
    set SUPABASE_SERVICE_KEY=<service_role key>

    python scripts/upload_plates.py --check     # what the DB expects vs what exists
    python scripts/upload_plates.py             # upload everything missing
    python scripts/upload_plates.py --force     # re-upload everything

Run `--check` first, every time. A plate the database references but the bucket
does not hold renders as a broken image with no console error and no failed
request in the app — the page simply looks wrong. This is the only step that
catches it, and it is free.

The service_role key bypasses row-level security and must never reach the
browser or the repo. It is read from the environment here and used for exactly
one thing: writing objects into the `plates` bucket. The web app uses only the
public URL, no key at all.
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

import requests

WEBP = dbmod.ROOT / "data" / "webp"
BUCKET = "plates"
CATALOGS = [dbmod.ROOT / "db" / "features.db", dbmod.ROOT / "db" / "pdp.db"]


def expected_keys() -> set[str]:
    """Every object key the two catalogs reference, in published form."""
    keys: set[str] = set()
    for path in CATALOGS:
        if not path.exists():
            continue
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            rows = con.execute(
                "SELECT screenshot_path, crop_path FROM annotations"
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        finally:
            con.close()
        for shot, crop in rows:
            for v, is_plate in ((shot, True), (crop, False)):
                if not v:
                    continue
                p = v.replace("\\", "/")
                p = p[len("data/screenshots/"):] if p.startswith("data/screenshots/") else p
                if p.lower().endswith(".png"):
                    p = p[:-4] + ".webp"
                keys.add(p)
                # Only a full plate has an un-circled twin. `annotate.py` writes
                # `<page>-clean.png` beside `<page>.png`, but crops are cut from
                # the finished plate and have no such pair -- asking for
                # `01-some-crop-clean.webp` invents 600-odd files that were never
                # meant to exist and buries any real gap in the noise.
                if is_plate and not p.endswith("-clean.webp"):
                    keys.add(p[:-5] + "-clean.webp")
    return keys


def local_keys() -> set[str]:
    if not WEBP.is_dir():
        return set()
    return {p.relative_to(WEBP).as_posix() for p in WEBP.rglob("*.webp")}


def upload(session: requests.Session, base: str, key: str, path: Path,
           force: bool) -> tuple[bool, str]:
    url = f"{base}/storage/v1/object/{BUCKET}/{key}"
    headers = {"Content-Type": "image/webp", "Cache-Control": "public, max-age=31536000"}
    if force:
        headers["x-upsert"] = "true"
    r = session.post(url, headers=headers, data=path.read_bytes(), timeout=120)
    if r.status_code in (200, 201):
        return True, ""
    if r.status_code == 409 and not force:
        return True, "exists"
    return False, f"HTTP {r.status_code}: {r.text[:160]}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Upload plates to Supabase Storage")
    ap.add_argument("--check", action="store_true",
                    help="compare what the catalogs expect against what exists")
    ap.add_argument("--force", action="store_true", help="overwrite existing objects")
    ap.add_argument("--url", default=os.environ.get("SUPABASE_URL"))
    ap.add_argument("--key", default=os.environ.get("SUPABASE_SERVICE_KEY"))
    a = ap.parse_args()

    want = expected_keys()
    have = local_keys()
    missing = sorted(want - have)
    extra = len(have - want)

    print(f"  catalogs reference : {len(want)} objects")
    print(f"  converted locally  : {len(have)} objects  ({extra} not referenced)")
    if missing:
        print(f"\n  !! {len(missing)} referenced plate(s) have no WebP — run scripts/to_webp.py")
        for m in missing[:10]:
            print(f"       {m}")
        if len(missing) > 10:
            print(f"       … and {len(missing)-10} more")
    else:
        print("  every referenced plate has been converted")

    if a.check:
        return 1 if missing else 0

    if not a.url or not a.key:
        print("\nERROR: set SUPABASE_URL and SUPABASE_SERVICE_KEY", file=sys.stderr)
        return 2

    base = a.url.rstrip("/")
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {a.key}",
                            "apikey": a.key})

    todo = sorted(have & want) if not a.force else sorted(have & want)
    ok = skip = fail = 0
    sent = 0
    for i, key in enumerate(todo, 1):
        path = WEBP / key
        good, note = upload(session, base, key, path, a.force)
        if good and note == "exists":
            skip += 1
        elif good:
            ok += 1
            sent += path.stat().st_size
        else:
            fail += 1
            print(f"  FAIL {key}: {note}", file=sys.stderr)
        if i % 50 == 0:
            print(f"  [{i}/{len(todo)}] uploaded {ok}, already present {skip}, failed {fail}")

    print(f"\n  uploaded {ok} ({sent/1048576:.0f} MB), already present {skip}, failed {fail}")
    print(f"  public base: {base}/storage/v1/object/public/{BUCKET}")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
