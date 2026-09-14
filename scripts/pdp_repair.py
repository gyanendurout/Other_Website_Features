"""Repair mechanically-broken evidence strings in extracted PDP JSON.

    python scripts/pdp_repair.py --dry-run      # show what would change
    python scripts/pdp_repair.py                # apply

Three rules, each fixing a failure mode that is invisible until the annotator
reports `0/N circled`:

1. SCRAPER ARTIFACT. Firecrawl appends its own summary line to a page that
   carries review structured data:

       **Overall rating:** 4.6460233 / 5 from 1647 reviews.

   That sentence is assembled from JSON-LD and is *never rendered*, so no needle
   built from it can ever match. Worse, it can be flatly wrong: on myobvi it says
   "0.0 / 5 from 0 reviews" while the page itself renders "4.15/ 5 (4640)".
   Evidence quoting it is demoted and marked, never silently kept.

2. COMPOSITE NEEDLE. Evidence joined with " | ", " - " or " / " is usually a
   label and its value from two different elements ("Color - Grey",
   "Country/region United States | USD $"). The longest fragment that actually
   occurs in the capture replaces the whole string. Em dashes are left alone --
   in prose ("Glider 2026 - In Stock Now" with an em dash) they are part of one
   rendered string, not a joiner.

3. SHORT NEEDLE. Under 8 characters ("ADD", "4.5", "Log in") will match
   somewhere on any storefront. The feature is kept -- it is real -- but its
   confidence drops to 0.6 so the UI presents it as weak rather than certain.

Nothing is deleted. Being un-circled is an honest outcome; a needle bent until
it matches the wrong element is not.
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
MARKDOWN_DIR = db.ROOT / "data" / "pdp" / "markdown"

# Firecrawl's injected structured-data summary. Never on the page. Matched
# without requiring the "Overall rating:" prefix, because extractors quote the
# tail of the sentence just as often as the whole of it.
ARTIFACT = re.compile(r"(?:overall rating:?\s*)?[\d.]+\s*/\s*5\s*from\s*\d+\s*reviews?",
                      re.I)
# joining separators only -- deliberately no em/en dash, see module docstring
JOINER = re.compile(r"\s+(?:\||/|-)\s+")
RE_MD = re.compile(r"[*_`~]+")
RE_SYM = re.compile(r"[™®©‘’“”]")
RE_WS = re.compile(r"\s+")
MIN_LEN = 8
MIN_FRAGMENT = 12


def norm(t: str) -> str:
    return RE_WS.sub(" ", RE_SYM.sub("", RE_MD.sub("", t or ""))).strip()


def _trim(part: str) -> str:
    """Strip surrounding quotes, and brackets only when they are unbalanced.

    Stripping "()" unconditionally turns "Magnesium (as magnesium malate)" into
    "Magnesium (as magnesium malate" -- a needle with an unclosed bracket that
    matches nothing.
    """
    p = part.strip().strip("\"'").strip()
    while p and p[0] in "([" and p.count(p[0]) > p.count({"(": ")", "[": "]"}[p[0]]):
        p = p[1:].strip()
    while p and p[-1] in ")]" and p.count(p[-1]) > p.count({")": "(", "]": "["}[p[-1]]):
        p = p[:-1].strip()
    return p


def capture(domain: str) -> str:
    d = MARKDOWN_DIR / domain
    if not d.is_dir():
        return ""
    return norm(" ".join(p.read_text(encoding="utf-8", errors="replace")
                         for p in d.glob("*.md"))).lower()


def repair(path: Path, apply: bool) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    hay = capture(path.stem)
    changes = 0

    for f in data.get("features", []):
        ev = (f.get("evidence") or "").strip()
        if not ev:
            continue
        before = (ev, f.get("confidence"))

        # 1. scraper artifact
        if ARTIFACT.search(ev):
            f["confidence"] = min(float(f.get("confidence") or 1), 0.6)
            note = ("Only the scraper's structured-data summary carried this, not "
                    "rendered text, so it cannot be circled.")
            if note not in (f.get("description") or ""):
                f["description"] = f"{(f.get('description') or '').rstrip('.')}. {note}"
            print(f"    artifact  {f['name'][:40]:<40} conf -> {f['confidence']}")
            changes += 1
            continue

        # 2. composite needle -> the RAREST fragment that is really in the capture.
        #
        # Not the longest. On a PDP the longest fragment is almost always the
        # product title, which is also the single most repeated string on the
        # page -- so "Variety Pack | 1 Time Purchase" would resolve to the H1 and
        # circle the wrong element while reporting a confident hit. Occurrence
        # count is the signal that actually tracks distinctiveness.
        if JOINER.search(ev):
            parts = [_trim(p) for p in JOINER.split(ev)]
            found = [p for p in parts
                     if len(p) >= MIN_FRAGMENT and (not hay or norm(p).lower() in hay)]
            if found:
                best = min(found, key=lambda p: (hay.count(norm(p).lower()), -len(p)))
                f["evidence"] = best
                print(f"    split     {f['name'][:40]:<40} {ev[:34]!r} -> {best[:34]!r}")
                changes += 1
            else:
                f["confidence"] = min(float(f.get("confidence") or 1), 0.6)
                print(f"    composite {f['name'][:40]:<40} no usable fragment, conf -> 0.6")
                changes += 1
            ev = f["evidence"]

        # 3. short needle
        if len(ev) < MIN_LEN and float(f.get("confidence") or 1) > 0.6:
            f["confidence"] = 0.6
            print(f"    short     {f['name'][:40]:<40} {ev!r} conf -> 0.6")
            changes += 1

        if (f.get("evidence"), f.get("confidence")) != before:
            pass

    if changes and apply:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    return changes


def main() -> int:
    ap = argparse.ArgumentParser(description="Repair PDP evidence strings")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("files", nargs="*")
    a = ap.parse_args()

    paths = [Path(f) for f in a.files] or sorted(RAW_DIR.glob("*.json"))
    total = 0
    for p in paths:
        print(f"  {p.name}")
        n = repair(p, apply=not a.dry_run)
        total += n
        if not n:
            print("    nothing to repair")
    verb = "would change" if a.dry_run else "changed"
    print(f"\n  {verb} {total} feature(s) across {len(paths)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
