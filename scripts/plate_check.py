"""Compare each clean plate against its annotated twin and flag bad captures.

    python scripts/plate_check.py                      # every domain in the catalog
    python scripts/plate_check.py --site arrae.com

`annotate.py` writes `<page>-clean.png` first and cuts its crops from
`<page>.png`. Anything that lands between the two shots -- a popup on a timer is
the usual culprit -- ruins only the second plate, while the run still prints a
healthy "8/12 circled". That failure mode shipped nine solid-white crops once
already, so the count alone is not evidence of a good capture.

Two cheap signals catch it:

  size   an annotated plate much shorter than its clean twin means content did
         not paint, or a scroll-locked body clipped the full-page capture
  bright a dimmer behind a modal darkens the whole plate (one PDP went from
         mean 120 to mean 30 this way); a blown-out one went solid white

Exit code is 1 if anything is suspect, so it can gate a pipeline.
"""
from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db

from PIL import Image

Image.MAX_IMAGE_PIXELS = None          # PDP plates run past the decompression guard

# A plate more than this fraction shorter than its clean twin did not paint.
HEIGHT_TOLERANCE = 0.12
# Mean luminance outside this band is a dimmer, a white-out, or a bot wall.
DARK_FLOOR = 40
BRIGHT_CEIL = 250
# Below this, a full-page capture almost certainly got clipped to the viewport.
MIN_BYTES = 60_000


def stats(path: Path) -> tuple[int, int, float]:
    """(width, height, mean luminance) of a plate, downsampled for speed."""
    with Image.open(path) as im:
        w, h = im.size
        # a 20,000px plate takes seconds to mean() at full size and the answer
        # is identical at 1/16 scale
        small = im.convert("L").reduce(16) if max(w, h) > 4000 else im.convert("L")
        px = list(small.getdata())
    return w, h, (sum(px) / len(px)) if px else 0.0


def check(domain: str) -> list[str]:
    """Report lines for one domain; a line starting with '!!' is a problem."""
    out: list[str] = []
    shot_dir = db.SHOT_DIR / domain
    if not shot_dir.is_dir():
        return [f"!!  {domain}: no plate directory at {shot_dir}"]

    plates = sorted(p for p in shot_dir.glob("*.png") if not p.stem.endswith("-clean"))
    if not plates:
        return [f"!!  {domain}: no annotated plates"]

    for shot in plates:
        clean = shot.with_name(f"{shot.stem}-clean.png")
        aw, ah, amean = stats(shot)
        line = f"    {shot.name:<46} {aw}x{ah}  mean {amean:5.1f}  {shot.stat().st_size/1024:7.0f} KB"
        problems = []

        if shot.stat().st_size < MIN_BYTES:
            problems.append(f"only {shot.stat().st_size/1024:.0f} KB - likely a bot wall or clipped capture")
        if amean < DARK_FLOOR:
            problems.append(f"mean luminance {amean:.0f} - a modal dimmer probably covered the page")
        if amean > BRIGHT_CEIL:
            problems.append(f"mean luminance {amean:.0f} - plate is effectively blank")

        if clean.exists():
            cw, ch, cmean = stats(clean)
            line += f"   (clean {cw}x{ch} mean {cmean:5.1f})"
            if ch and ah < ch * (1 - HEIGHT_TOLERANCE):
                problems.append(
                    f"annotated plate is {100*(1-ah/ch):.0f}% shorter than the clean one "
                    "- content did not paint, or a popup locked body scrolling"
                )
            if cmean and amean < cmean * 0.55:
                problems.append(
                    f"annotated plate is much darker than the clean one "
                    f"({amean:.0f} vs {cmean:.0f}) - something arrived between the two shots"
                )
        else:
            problems.append("no clean plate to compare against")

        out.append(line)
        out.extend(f"!!      {p}" for p in problems)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Sanity-check annotated plates")
    ap.add_argument("--site", help="one domain; default is every site in the catalog")
    args = ap.parse_args()

    con = db.connect()
    domains = (
        [args.site]
        if args.site
        else [r["domain"] for r in con.execute("SELECT domain FROM sites ORDER BY domain")]
    )
    con.close()

    print(f"plates under {db.SHOT_DIR}\n")
    bad = 0
    for d in domains:
        lines = check(d)
        print(f"  {d}")
        for ln in lines:
            print(ln)
            if ln.lstrip().startswith("!!"):
                bad += 1
        print()

    print(f"{'OK - nothing suspect' if not bad else f'{bad} problem(s) found'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
