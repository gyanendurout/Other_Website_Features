"""Validate extracted PDP JSON before it ever reaches the database.

    python scripts/pdp_validate.py                       # every file
    python scripts/pdp_validate.py data/pdp/raw/arrae.com.json

Checks the rules from REQUIREMENTS.md section 3 that are mechanically checkable,
because each of them fails *silently* otherwise:

  composite evidence   joined with " - ", "...", " | ", " / " -- reads well,
                       matches nothing. Cost a 7/19 match rate once.
  evidence not in the  if the needle is not in the captured markdown it is very
  capture              unlikely to be in the live DOM either
  source_url mismatch  a feature whose URL is not a scraped page can never be
                       linked to a page, so it can never be circled
  slug-shaped evidence url-slug-like strings never appear as on-page text
  unknown canonical    a synonym invents a fake gap in the comparison matrix
  bad category         breaks the grouping in the UI
  too-short / generic  needles that will match the wrong element

Nothing here is fatal on its own -- the point is to print the list so it can be
fixed deliberately rather than discovered as "0/N circled" an hour later.
"""
from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import json
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db

RAW_DIR = db.ROOT / "data" / "pdp" / "raw"
CANONICAL_MD = db.ROOT / "data" / "pdp" / "canonical.md"
MARKDOWN_DIR = db.ROOT / "data" / "pdp" / "markdown"

CATEGORIES = {
    "conversion", "payments", "social-proof", "product-info", "media", "trust",
    "fulfilment", "personalisation", "loyalty", "support", "content", "navigation",
}

# the separators that betray a quote stitched from several DOM elements
COMPOSITE = re.compile(r"\s(?:-|–|—|\||/|\.\.\.|…)\s")
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+){2,}$")
RE_MD = re.compile(r"[*_`~]+")
RE_SYM = re.compile(r"[™®©‘’“”]")
RE_WS = re.compile(r"\s+")
GENERIC = {
    "with", "from", "that", "this", "their", "product", "products", "page",
    "site", "section", "content", "options", "available", "shipping", "support",
    "featured", "pricing", "customer", "customers", "shopping", "checkout",
    "category", "collection", "collections",
}


def norm(text: str) -> str:
    return RE_WS.sub(" ", RE_SYM.sub("", RE_MD.sub("", text or ""))).strip().lower()


def canonical_vocabulary() -> set[str]:
    """Every canonical name listed in canonical.md, normalised.

    Entries are separated by "·" and wrap freely across lines, so each category
    block must be joined into one string *before* splitting. Splitting per line
    instead cuts "Subscription Frequency Choice" in half and then reports both
    halves as unknown names -- which is a bug in the checker that looks exactly
    like sloppy extraction.
    """
    if not CANONICAL_MD.exists():
        return set()

    body = CANONICAL_MD.read_text(encoding="utf-8")
    # keep only the category blocks: everything after the first "## " heading
    blocks = re.split(r"^##\s+.*$", body, flags=re.M)[1:]
    names: set[str] = set()
    for block in blocks:
        # drop prose lines; entry lines are the ones carrying "·" or sitting
        # inside a run of them
        flat = RE_WS.sub(" ", block)
        for part in flat.split("·"):
            part = part.strip().strip("*_`").rstrip(".")
            if 2 < len(part) < 60 and not part.startswith(("#", ">", "|")):
                names.add(norm(part))
    return names


def capture_text(domain: str) -> str:
    """Both engines' markdown for a domain, concatenated and normalised."""
    d = MARKDOWN_DIR / domain
    if not d.is_dir():
        return ""
    return norm(" ".join(p.read_text(encoding="utf-8", errors="replace")
                         for p in d.glob("*.md")))


def scraped_urls() -> set[str]:
    con = db.connect()
    urls = {r["url"] for r in con.execute("SELECT url FROM pages")}
    con.close()
    return urls


def validate(path: Path, vocab: set[str], urls: set[str]) -> tuple[int, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    site = data.get("site") or {}
    feats = data.get("features") or []
    domain = path.stem
    hay = capture_text(domain)

    problems: list[str] = []
    warnings: list[str] = []

    for key in ("url", "name"):
        if not site.get(key):
            problems.append(f"site.{key} is missing")

    seen: set[str] = set()
    for i, f in enumerate(feats):
        tag = f"[{i:>2}] {(f.get('name') or '?')[:44]}"

        name = f.get("name") or ""
        if not name:
            problems.append(f"{tag}: no name")
        if name.lower() in seen:
            problems.append(f"{tag}: duplicate name (UNIQUE(site_id,name) will collapse it)")
        seen.add(name.lower())

        cat = f.get("category")
        if cat not in CATEGORIES:
            problems.append(f"{tag}: category {cat!r} is not one of the twelve")

        canon = f.get("canonical")
        if not canon:
            problems.append(f"{tag}: no canonical name - it will not appear in the matrix")
        elif vocab and norm(canon) not in vocab:
            warnings.append(f"{tag}: canonical {canon!r} is not in canonical.md (proposed?)")

        if f.get("source_url") not in urls:
            problems.append(f"{tag}: source_url is not a scraped page -> can never be circled")

        conf = f.get("confidence")
        if conf is None or not (0 <= float(conf) <= 1):
            problems.append(f"{tag}: confidence {conf!r} out of range")

        ev = (f.get("evidence") or "").strip()
        if not ev:
            problems.append(f"{tag}: no evidence")
            continue

        if COMPOSITE.search(ev):
            problems.append(
                f"{tag}: evidence looks stitched from separate elements -> {ev[:70]!r}"
            )
        if SLUG.match(ev.lower()):
            problems.append(f"{tag}: evidence is a url slug, never on-page text -> {ev!r}")
        if len(ev) < 8:
            problems.append(f"{tag}: evidence {ev!r} is too short to be distinctive")
        words = [w for w in norm(ev).split() if w]
        if words and all(w in GENERIC for w in words):
            warnings.append(f"{tag}: evidence is all generic words -> {ev!r}")

        # the strongest signal available without touching the network
        if hay and norm(ev) not in hay:
            level = warnings if float(conf or 1) <= 0.7 else problems
            level.append(f"{tag}: evidence not found in either capture -> {ev[:70]!r}")

    print(f"  {path.name:<28} {len(feats):>3} features")
    for p in problems:
        print(f"  !!   {p}")
    for w in warnings:
        print(f"  ~    {w}")
    if not problems and not warnings:
        print("       clean")
    print()
    return len(problems), len(warnings)


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate extracted PDP JSON")
    ap.add_argument("files", nargs="*", help="default: every file in data/pdp/raw")
    args = ap.parse_args()

    paths = [Path(f) for f in args.files] or sorted(RAW_DIR.glob("*.json"))
    if not paths:
        print(f"no JSON files in {RAW_DIR}")
        return 1

    vocab = canonical_vocabulary()
    urls = scraped_urls()
    print(f"{len(paths)} file(s) · {len(vocab)} canonical names · {len(urls)} scraped pages\n")

    bad = warn = total = 0
    for p in paths:
        b, w = validate(p, vocab, urls)
        bad += b
        warn += w
        total += len(json.loads(p.read_text(encoding='utf-8')).get("features") or [])

    print(f"{total} features · {bad} problem(s) · {warn} warning(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
