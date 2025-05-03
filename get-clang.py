#!/usr/bin/env python3
"""
download_clang_reference.py

Fetch https://clang.llvm.org/docs/ClangCommandLineReference.html
and save it, unchanged, to the directory given on the command line.
"""

import argparse
import time
from pathlib import Path
import requests

URL = "https://clang.llvm.org/docs/ClangCommandLineReference.html"
FILENAME = "ClangCommandLineReference.html"
PAUSE_SECONDS = 60      # one request only, but we keep the same etiquette


def download(url: str, target: Path) -> None:
    """Fetch *url* and write it to *target* (UTF-8 text)."""
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    target.write_text(r.text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download the Clang command-line reference page."
    )
    parser.add_argument(
        "directory",
        help="Destination directory (created if needed)",
    )
    args = parser.parse_args()

    dest_dir = Path(args.directory).expanduser().resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    outfile = dest_dir / FILENAME
    print(f"Downloading {URL} → {outfile}")
    try:
        download(URL, outfile)
    except Exception as exc:
        print(f"⚠️  Download failed: {exc}")
        raise SystemExit(1)

    print(f"✔️  Saved. Waiting {PAUSE_SECONDS} s as a courtesy …")
    time.sleep(PAUSE_SECONDS)
    print("Finished.")


if __name__ == "__main__":
    main()
