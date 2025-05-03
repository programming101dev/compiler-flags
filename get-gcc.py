#!/usr/bin/env python3
"""
download_gcc_chapters.py

Fetch the mini-TOC from

  https://gcc.gnu.org/onlinedocs/gcc-15.1.0/gcc/Invoking-GCC.html

and download every linked chapter HTML file – *including* all architecture
pages referenced from Submodel-Options.html – into the directory given with
  -o / --output <dir>.

A 60-second courtesy pause is kept between requests.
"""

from __future__ import annotations

import argparse
import os
import time
import urllib.parse
from pathlib import Path
from typing import List, Set

import requests
from bs4 import BeautifulSoup

BASE_DIR  = "https://gcc.gnu.org/onlinedocs/gcc-15.1.0/gcc/"
TOP_PAGE  = urllib.parse.urljoin(BASE_DIR, "Invoking-GCC.html")
META_FILE = "Submodel-Options.html"        # architecture “meta” chapter

SKIP_FILES: Set[str] = {"Option-Summary.html"}    # never download
PAUSE_SECONDS = 120


# ───────────────────────── helpers ──────────────────────────
def _download(url: str, dest: Path) -> None:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    dest.write_text(r.text, encoding="utf-8")


def _mini_toc_hrefs(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    toc = soup.find("ul", class_="mini-toc")
    if toc is None:
        return []
    return [a["href"] for a in toc.find_all("a", href=True)]


# ───────────────────── collect work list ────────────────────
def fetch_main_toc() -> List[str]:
    resp = requests.get(TOP_PAGE, timeout=30)
    resp.raise_for_status()
    return [
        h for h in _mini_toc_hrefs(resp.text)
        if os.path.basename(h) not in SKIP_FILES
    ]


def fetch_arch_toc(meta_url: str) -> List[str]:
    resp = requests.get(meta_url, timeout=30)
    resp.raise_for_status()
    return [h for h in _mini_toc_hrefs(resp.text) if h.endswith(".html")]


def build_work_list() -> List[str]:
    work: List[str] = []
    seen: Set[str] = set()

    for href in fetch_main_toc():
        if href in seen:
            continue
        seen.add(href)
        work.append(href)

        if os.path.basename(href) == META_FILE:         # add sub-pages
            meta_url = urllib.parse.urljoin(BASE_DIR, href)
            for sub in fetch_arch_toc(meta_url):
                if sub not in seen and os.path.basename(sub) not in SKIP_FILES:
                    seen.add(sub)
                    work.append(sub)

    return work


# ─────────────────────────── CLI ────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(
        description="Download GCC-15.1 invocation chapters "
                    "(including architecture-specific pages)."
    )
    ap.add_argument("-o", "--output", required=True, type=Path,
                    help="Directory to save downloaded HTML files")

    args = ap.parse_args()
    out_dir: Path = args.output.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    hrefs = build_work_list()
    total = len(hrefs)

    for idx, href in enumerate(hrefs, start=1):
        url     = urllib.parse.urljoin(BASE_DIR, href)
        outfile = out_dir / os.path.basename(href)

        print(f"[{idx}/{total}] {url}  →  {outfile}")
        try:
            _download(url, outfile)
            print(f"      ✔ saved. Sleeping {PAUSE_SECONDS}s …")
        except Exception as exc:
            print(f"      ⚠️  failed: {exc}")
        time.sleep(PAUSE_SECONDS)

    print("Finished.")


if __name__ == "__main__":
    main()
