"""Bulk-insert analyzed features from a JSON file.

    python scripts/add_features.py data/raw/stripe.json

JSON shape:
{
  "site":  {"url":"https://stripe.com","name":"Stripe","vertical":"fintech",
            "business_model":"usage-based","tagline":"...","description":"..."},
  "features":[
    {"name":"Single Sign-On (SAML)","canonical":"Single Sign-On","category":"auth",
     "description":"...","evidence":"quote from page","confidence":0.9,
     "tier":"enterprise","is_differentiator":0,"source_url":"https://..."}
  ]
}
"""
from __future__ import annotations

import sys
if hasattr(sys.stdout, "reconfigure"):      # Windows console is cp1252
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db


def load(con, payload: dict) -> tuple[int, int]:
    site = payload["site"]
    site_id = db.upsert_site(
        con, site["url"],
        name=site.get("name"), vertical=site.get("vertical"),
        business_model=site.get("business_model"), tagline=site.get("tagline"),
        description=site.get("description"), notes=site.get("notes"),
    )

    # map source_url -> page_id so features point at the page they came from
    pages = {r["url"]: r["id"] for r in
             con.execute("SELECT id, url FROM pages WHERE site_id = ?", (site_id,))}

    added = skipped = 0
    for f in payload.get("features", []):
        name = (f.get("name") or "").strip()
        if not name:
            skipped += 1
            continue
        db.add_feature(
            con, site_id, name,
            page_id=pages.get(f.get("source_url")),
            canonical=f.get("canonical"),
            category=f.get("category"),
            description=f.get("description"),
            evidence=f.get("evidence"),
            confidence=f.get("confidence"),
            tier=f.get("tier"),
            is_differentiator=int(bool(f.get("is_differentiator"))),
        )
        added += 1
    return added, skipped


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    con = db.connect()
    total_a = total_s = 0
    for path in sys.argv[1:]:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        a, s = load(con, payload)
        total_a += a
        total_s += s
        print(f"  {payload['site'].get('name') or payload['site']['url']}: "
              f"+{a} features" + (f" ({s} skipped)" if s else ""))
    con.close()
    print(f"\n  TOTAL: +{total_a} features")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
