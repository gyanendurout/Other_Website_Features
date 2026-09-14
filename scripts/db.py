"""Shared SQLite helpers for the website feature catalog."""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent


def _path(env: str, *default: str) -> Path:
    """A data path, overridable by env var. Relative overrides resolve on ROOT,
    so CATALOG_DB=db/pdp.db works from any working directory."""
    raw = os.environ.get(env)
    p = Path(raw) if raw else Path(*default)
    return p if p.is_absolute() else ROOT / p


# A second catalog (e.g. the PDP Lab) is a matter of pointing these three
# somewhere else; nothing else in the pipeline needs to know.
DB_PATH = _path("CATALOG_DB", "db", "features.db")
MARKDOWN_DIR = _path("CATALOG_MARKDOWN", "data", "markdown")
SHOT_DIR = _path("CATALOG_SHOTS", "data", "screenshots")
SCHEMA_PATH = ROOT / "scripts" / "schema.sql"


def connect() -> sqlite3.Connection:
    """Open the catalog, creating it from schema.sql if missing."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return con


def domain_of(url: str) -> str:
    """Canonical domain key: lowercase, no www, no port."""
    host = (urlparse(url).hostname or url).lower()
    return host[4:] if host.startswith("www.") else host


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def upsert_site(con: sqlite3.Connection, url: str, **fields) -> int:
    """Insert or update a site, returning its id. Only non-None fields overwrite."""
    domain = domain_of(url)
    con.execute(
        "INSERT INTO sites (domain, homepage_url) VALUES (?, ?) "
        "ON CONFLICT(domain) DO NOTHING",
        (domain, url),
    )
    allowed = {"name", "vertical", "business_model", "tagline", "description", "notes"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if updates:
        sets = ", ".join(f"{k} = ?" for k in updates)
        con.execute(
            f"UPDATE sites SET {sets} WHERE domain = ?",
            (*updates.values(), domain),
        )
    con.commit()
    return con.execute("SELECT id FROM sites WHERE domain = ?", (domain,)).fetchone()["id"]


def upsert_page(con: sqlite3.Connection, site_id: int, url: str, **fields) -> int:
    """Insert or update a scraped page row, returning its id."""
    cols = ["title", "page_type", "markdown_path", "content_hash",
            "word_count", "http_status", "scrape_status", "error"]
    vals = {c: fields.get(c) for c in cols}
    con.execute(
        "INSERT INTO pages (site_id, url) VALUES (?, ?) ON CONFLICT(url) DO NOTHING",
        (site_id, url),
    )
    sets = ", ".join(f"{c} = COALESCE(?, {c})" for c in cols)
    con.execute(
        f"UPDATE pages SET {sets}, scraped_at = datetime('now') WHERE url = ?",
        (*[vals[c] for c in cols], url),
    )
    con.execute(
        "UPDATE sites SET last_scraped_at = datetime('now') WHERE id = ?", (site_id,)
    )
    con.commit()
    return con.execute("SELECT id FROM pages WHERE url = ?", (url,)).fetchone()["id"]


def add_feature(con: sqlite3.Connection, site_id: int, name: str,
                page_id: int | None = None, canonical: str | None = None,
                **fields) -> int:
    """Insert or update one feature. Optionally link it to a canonical concept."""
    cols = ["category", "description", "evidence", "confidence", "tier",
            "is_differentiator"]
    vals = [fields.get(c) for c in cols]
    con.execute(
        "INSERT INTO features (site_id, page_id, name) VALUES (?, ?, ?) "
        "ON CONFLICT(site_id, name) DO NOTHING",
        (site_id, page_id, name),
    )
    sets = ", ".join(f"{c} = COALESCE(?, {c})" for c in cols)
    con.execute(
        f"UPDATE features SET {sets}, page_id = COALESCE(?, page_id) "
        "WHERE site_id = ? AND name = ?",
        (*vals, page_id, site_id, name),
    )
    row = con.execute(
        "SELECT id FROM features WHERE site_id = ? AND name = ?", (site_id, name)
    ).fetchone()
    feature_id = row["id"]

    if canonical:
        slug = slugify(canonical)
        con.execute(
            "INSERT INTO canonical_features (slug, name, category) VALUES (?, ?, ?) "
            "ON CONFLICT(slug) DO NOTHING",
            (slug, canonical, fields.get("category")),
        )
        cid = con.execute(
            "SELECT id FROM canonical_features WHERE slug = ?", (slug,)
        ).fetchone()["id"]
        con.execute(
            "INSERT OR IGNORE INTO feature_links (feature_id, canonical_id) VALUES (?, ?)",
            (feature_id, cid),
        )
    con.commit()
    return feature_id
