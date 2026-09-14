"""Convert catalog screenshots to WebP for online delivery.

    python scripts/to_webp.py                 # convert everything not yet done
    python scripts/to_webp.py --force
    python scripts/to_webp.py --dry-run

Why: the catalog holds ~695 MB of PNG across 756 files, with single full-page
plates up to 21.7 MB and 30,668 px tall. That is too much for a Git repo and too
much to push through a Vercel deploy.

## Two constraints decide the output size, and they interact

**WebP cannot encode a dimension over 16,383 px.** 28 plates in this catalog
exceed that -- the tallest is 2972 x 30668 -- so "same pixels, just WebP" is not
an available option. They would simply fail to encode.

**The annotation overlay derives document geometry from the image.**
`plate.tsx` and `viewer.tsx` compute CSS pixels as `naturalWidth / SCALE` and
place every circle as a percentage of that. Change the served resolution without
changing SCALE and every circle moves, silently, with no error anywhere.

Halving resolves both at once. Plates are captured at `device_scale_factor = 2`
(see `annotate.py`), so halving returns them to DPR 1: the tallest becomes
15,334 px and fits, the pixel count drops 4x, and `SCALE` becomes exactly 1.

**If you change HALVE here, you must change SCALE in both viewer components in
the same commit.** They are one decision expressed in two languages.

Originals are never touched. Output mirrors the input tree under data/webp/.
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

Image.MAX_IMAGE_PIXELS = None          # 30,000px plates exceed the default guard

SRC = db.ROOT / "data" / "screenshots"
OUT = db.ROOT / "data" / "webp"

HALVE = 2          # captured at DPR 2; serve at DPR 1. See the module docstring.
WEBP_MAX = 16383   # hard limit in the WebP container format


def convert(src: Path, dst: Path, quality: int) -> tuple[int, int, str]:
    """Write one WebP at 1/HALVE scale. Returns (src bytes, out bytes, note)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    note = ""
    with Image.open(src) as im:
        im = im.convert("RGB")          # plates have no alpha worth carrying
        w, h = im.size
        tw, th = max(1, w // HALVE), max(1, h // HALVE)

        # Belt and braces: a plate tall enough to still breach the limit after
        # halving would fail to encode with a confusing error deep in Pillow.
        if max(tw, th) > WEBP_MAX:
            shrink = max(tw, th) / WEBP_MAX
            tw, th = int(tw / shrink), int(th / shrink)
            note = f" (extra shrink {shrink:.2f}x — GEOMETRY WILL BE WRONG)"

        im = im.resize((tw, th), Image.LANCZOS)
        im.save(dst, "WEBP", quality=quality, method=6)
    return src.stat().st_size, dst.stat().st_size, note


def main() -> int:
    ap = argparse.ArgumentParser(description="Convert screenshots to WebP at DPR 1")
    ap.add_argument("--quality", type=int, default=82)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    pngs = sorted(SRC.rglob("*.png"))
    if not pngs:
        print(f"no PNGs under {SRC}")
        return 1

    total_src = sum(p.stat().st_size for p in pngs)
    print(f"  {len(pngs)} PNG · {total_src/1048576:.0f} MB under {SRC}")
    print(f"  -> {OUT}   quality {a.quality}, scaled 1/{HALVE} (DPR 2 -> DPR 1)\n")
    if a.dry_run:
        return 0

    done = skipped = failed = 0
    sum_src = sum_out = 0
    warned: list[str] = []

    for i, p in enumerate(pngs, 1):
        rel = p.relative_to(SRC)
        dst = OUT / rel.with_suffix(".webp")
        if dst.exists() and not a.force and dst.stat().st_mtime >= p.stat().st_mtime:
            skipped += 1
            sum_src += p.stat().st_size
            sum_out += dst.stat().st_size
            continue
        try:
            s, o, note = convert(p, dst, a.quality)
        except Exception as e:
            failed += 1
            print(f"  FAIL {rel}: {e}", file=sys.stderr)
            continue
        if note:
            warned.append(f"{rel}{note}")
        sum_src += s
        sum_out += o
        done += 1
        if s > 4_000_000:
            print(f"  [{i:>3}/{len(pngs)}] {s/1048576:6.1f} -> {o/1048576:5.2f} MB  {rel}{note}")

    pct = (1 - sum_out / sum_src) * 100 if sum_src else 0
    print(f"\n  converted {done}, skipped {skipped}, failed {failed}")
    print(f"  {sum_src/1048576:.0f} MB -> {sum_out/1048576:.0f} MB  ({pct:.0f}% smaller)")
    if warned:
        print("\n  !! these needed more than a clean halving, so their overlay")
        print("     geometry will not line up — check them before publishing:")
        for w in warned:
            print(f"       {w}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
