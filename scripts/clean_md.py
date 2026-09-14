"""Strip scraper noise from markdown so feature extraction sees signal."""
from __future__ import annotations

import re

BS = chr(92)                                          # backslash, kept literal

RE_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")        # ![alt](url)
RE_EMPTY_LINK = re.compile(r"\[\s*\]\([^)]*\)")       # [](url) - was image-only
RE_EMPTY_HEAD = re.compile(r"^#{1,6}\s*$", re.MULTILINE)
RE_TRAIL_WS = re.compile(r"[ \t]+$", re.MULTILINE)
RE_BLANKS = re.compile(r"\n{3,}")
RE_LINK_OPEN = re.compile(r"\[\s*\n+")                # "[\n### \n" -> "["
RE_LINK_CLOSE = re.compile(r"\n+\]\(")                # "\n](url)"  -> "](url)"


def _strip_hard_breaks(md: str) -> str:
    """Drop markdown hard-break backslashes: whole lines and line-endings."""
    out = []
    for line in md.split("\n"):
        line = line.rstrip()
        while line.endswith(BS):                      # "Planning\" -> "Planning"
            line = line[:-1].rstrip()
        if line.strip() == "":
            continue
        out.append(line)
    return "\n".join(out)


def clean(md: str) -> str:
    md = RE_IMAGE.sub("", md)
    md = RE_EMPTY_LINK.sub("", md)
    md = _strip_hard_breaks(md)
    md = RE_LINK_OPEN.sub("[", md)                    # pull link text onto one line
    md = RE_LINK_CLOSE.sub("](", md)
    md = RE_EMPTY_HEAD.sub("", md)
    md = RE_TRAIL_WS.sub("", md)
    md = RE_BLANKS.sub("\n\n", md)

    # drop consecutive duplicate lines (repeated nav/footer)
    out, prev = [], None
    for line in md.split("\n"):
        s = line.strip()
        if s and s == prev:
            continue
        out.append(line)
        prev = s
    return "\n".join(out).strip() + "\n"


def stats(before: str, after: str) -> str:
    b, a = len(before.split()), len(after.split())
    pct = 0 if not b else round(100 * (b - a) / b)
    return f"{b} -> {a} words ({pct}% noise removed)"
