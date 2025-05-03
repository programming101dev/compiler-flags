#!/usr/bin/env python3
"""
parse_clang.py

Walk every *.html file under --input-dir, harvest the flags that appear
inside <dl class="std option"> blocks and emit JSON of the form

    {
      "<section heading>": [
        "-Wall",
        "--target",
        …
      ],
      …
    }

Headings are kept verbatim (after a little whitespace-/pilcrow-clean-up); any
later grouping or renaming can be done in a separate step.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Set

from bs4 import BeautifulSoup, Tag


# ──────────────────────────────────────────────────────────────────────────────
#  Normalisation helpers
# ──────────────────────────────────────────────────────────────────────────────
_HEADING_TAGS: Set[str] = {"h1", "h2", "h3", "h4", "h5", "h6"}

_RE_TRAILING_ANCHOR = re.compile(r"\s*¶\s*$")
_RE_PARENTHESES_TAIL = re.compile(r"\s*\([^)]*\)\s*$")
_RE_WS = re.compile(r"\s+")

_BAD_HEADING_CHARS = {
    "\u00C2",  # “Â”
    "\u00A0",  # NBSP
}

# -- flag clean-up: drop explanatory ( … ) tails ------------------------------
_PAREN = re.compile(r"\(.*")           # first '(' and everything after
_TRAIL_PAREN = re.compile(r"\)*\s*$")  # stray ')' at end


def _clean_heading(raw: str) -> str:
    """Return a tidy heading string suitable for use as a dict key."""
    txt = _RE_TRAILING_ANCHOR.sub("", raw)
    for ch in _BAD_HEADING_CHARS:
        txt = txt.replace(ch, " ")
    txt = "".join(" " if unicodedata.category(c) == "Zs" else c for c in txt)
    txt = _RE_WS.sub(" ", txt).strip()
    txt = _RE_PARENTHESES_TAIL.sub("", txt)
    return txt


def _clean_flag(flag: str) -> str:
    """Strip explanatory parentheses such as ‘(C, C++ only)’.  Flag text stays."""
    flag = _PAREN.sub("", flag)
    flag = _TRAIL_PAREN.sub("", flag)
    return flag.strip()


def _flags_from_dt(dt: Tag) -> List[str]:
    """Return every distinct flag string inside one <dt> element."""
    return [
        _clean_flag(span.get_text(strip=True))
        for span in dt.select("span.pre")
        if span.get_text(strip=True).startswith("-")
    ]


# ──────────────────────────────────────────────────────────────────────────────
#  Main scraping logic
# ──────────────────────────────────────────────────────────────────────────────
def _parse_html_file(path: Path) -> Dict[str, List[str]]:
    """Parse *one* HTML file and return {heading : [flags …]} extracted from it."""
    soup = BeautifulSoup(
        path.read_text(encoding="utf-8", errors="replace"), "html.parser"
    )

    current_heading = "Miscellaneous"
    mapping: Dict[str, List[str]] = {}

    for node in soup.body.descendants:
        if not isinstance(node, Tag):
            continue

        # ── heading? update the current key ──────────────────────────────────
        if node.name in _HEADING_TAGS:
            cleaned = _clean_heading(node.get_text(" ", strip=True))
            if cleaned:
                current_heading = cleaned
            continue

        # ── option list? gather the flags ────────────────────────────────────
        if node.name == "dl" and "option" in node.get("class", []):
            for dt in node.find_all("dt", recursive=False):
                for flag in _flags_from_dt(dt):
                    mapping.setdefault(current_heading, []).append(flag)

    return mapping


def _merge(parts: List[Dict[str, List[str]]]) -> Dict[str, List[str]]:
    """Merge many partial maps: deduplicate and sort the flag lists."""
    out: Dict[str, Set[str]] = {}
    for mp in parts:
        for heading, flags in mp.items():
            out.setdefault(heading, set()).update(flags)

    return {h: sorted(flags) for h, flags in out.items()}


# ──────────────────────────────────────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(
        description="Extract Clang command-line flags grouped by manual heading"
    )
    ap.add_argument(
        "--input-dir",
        required=True,
        type=Path,
        help="Directory containing Clang HTML reference files",
    )
    ap.add_argument(
        "--output",
        type=Path,
        help="Write JSON here instead of stdout",
    )
    args = ap.parse_args()

    html_files = list(args.input_dir.rglob("*.html"))
    if not html_files:
        ap.error(f"No .html files found under {args.input_dir}")

    collected = [_parse_html_file(f) for f in html_files]
    result = _merge(collected)

    json_text = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(json_text)
    else:
        print(json_text)


if __name__ == "__main__":
    main()
