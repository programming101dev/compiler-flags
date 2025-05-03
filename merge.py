#!/usr/bin/env python3
"""
merge_flags.py

Merge GCC and Clang flag lists into a single YAML mapping:

    <flag>:
      category     : <umbrella-category>
      gcc_category : <original GCC category, if seen>
      clang_category : <original Clang category, if seen>
      compilers    : [gcc, clang]
      has_arg      : true | false

Category mapping is applied from --categories. The first compiler to encounter
a flag assigns the umbrella category.

Usage:
    merge_flags.py --gcc gcc.yaml --clang clang.yaml --categories mapping.yaml -o merged.yaml
"""

from __future__ import annotations

import argparse
import re
import sys
import yaml
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List


# ──────────────────────────────────────────────────────────────────────────────
#  YAML helpers – ordered load & dump
# ──────────────────────────────────────────────────────────────────────────────
class _OrderedLoader(yaml.SafeLoader): pass
class _OrderedDumper(yaml.SafeDumper): pass

def _construct_mapping(loader: _OrderedLoader, node, deep=False):
    if not isinstance(node, yaml.MappingNode):
        raise yaml.constructor.ConstructorError(
            None, None, f"expected mapping node, got {node.id}", node.start_mark
        )
    loader.flatten_mapping(node)
    return OrderedDict(loader.construct_pairs(node, deep))

def _represent_ordered_dict(dumper: _OrderedDumper, data: OrderedDict):
    return dumper.represent_mapping(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, data.items())

_OrderedLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)
_OrderedDumper.add_representer(OrderedDict, _represent_ordered_dict)


def _load_yaml(path: Path) -> OrderedDict:
    with path.open(encoding="utf-8") as fh:
        data = yaml.load(fh, Loader=_OrderedLoader)
    if not isinstance(data, OrderedDict):
        raise ValueError(f"{path} does not contain a top-level mapping")
    return data

def _load_map_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a flat key-value mapping")
    return data

def _dump_yaml(obj: OrderedDict, fh) -> None:
    yaml.dump(obj, fh, Dumper=_OrderedDumper, sort_keys=False, default_flow_style=False, allow_unicode=True)


# ──────────────────────────────────────────────────────────────────────────────
#  Flag normalization
# ──────────────────────────────────────────────────────────────────────────────
RX_PARENS   = re.compile(r"\([^)]*\)\s*$")
RX_ARG_TAG  = re.compile(r"<[^>]*>\s*$")
RX_ELLIPSIS = re.compile(r"[…:]+\s*$")

def _normalise_flag(raw: str) -> tuple[str, bool]:
    flag = RX_PARENS.sub("", raw).rstrip()
    has_arg = False
    if "=" in flag:
        flag, _ = flag.split("=", 1)
        has_arg = True
    if RX_ARG_TAG.search(flag):
        flag = RX_ARG_TAG.sub("", flag)
        has_arg = True
    flag = RX_ELLIPSIS.sub("", flag).rstrip()
    return flag, has_arg


# ──────────────────────────────────────────────────────────────────────────────
#  Merge logic
# ──────────────────────────────────────────────────────────────────────────────
def _merge(
    gcc: OrderedDict[str, List[str]],
    clang: OrderedDict[str, List[str]],
    catmap: Dict[str, str],
    ignore_target: bool = False,
    ignore_developer: bool = False,
) -> OrderedDict[str, Dict[str, object]]:
    out: OrderedDict[str, Dict[str, object]] = OrderedDict()

    def ingest(src: OrderedDict[str, List[str]], compiler: str) -> None:
        for orig_cat, flags in src.items():
            mapped_cat = catmap.get(orig_cat, orig_cat)
            for raw in flags:
                flag, has_arg = _normalise_flag(raw)
                entry = out.setdefault(flag, {
                    "compilers": [],
                    "has_arg": False,
                })

                if "category" not in entry:
                    entry["category"] = mapped_cat

                if compiler not in entry["compilers"]:
                    entry["compilers"].append(compiler)

                if has_arg:
                    entry["has_arg"] = True

                if compiler == "gcc":
                    entry["gcc_category"] = orig_cat
                elif compiler == "clang":
                    entry["clang_category"] = orig_cat

    ingest(gcc, "gcc")
    ingest(clang, "clang")

    for flag, entry in out.items():
        cat = entry["category"]
        if (ignore_target and cat.startswith("target")) or (
            ignore_developer and cat.startswith("developer")
        ):
            entry["include"] = False

    return out


# ──────────────────────────────────────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(description="Merge GCC & Clang flag YAML files into one canonical list.")
    ap.add_argument("--gcc", required=True, type=Path, help="GCC flags YAML")
    ap.add_argument("--clang", required=True, type=Path, help="Clang flags YAML")
    ap.add_argument("--categories", required=True, type=Path, help="Category mapping YAML")
    ap.add_argument("-o", "--output", required=True, type=Path, help="Output merged YAML")
    ap.add_argument("--ignore-target", action="store_true",
                    help="Set 'include: false' on any flags whose category starts with 'target'")
    ap.add_argument("--ignore-developer", action="store_true",
                    help="Set 'include: false' on any flags whose category starts with 'developer'")
    args = ap.parse_args()

    try:
        gcc_data   = _load_yaml(args.gcc)
        clang_data = _load_yaml(args.clang)
        catmap     = _load_map_yaml(args.categories)
    except Exception as exc:
        sys.exit(f"❌  failed to read input: {exc}")

    new_flags = _merge(
        gcc_data,
        clang_data,
        catmap,
        ignore_target=args.ignore_target,
        ignore_developer=args.ignore_developer,
    )

    existing: OrderedDict[str, dict] = OrderedDict()
    if args.output.exists():
        try:
            existing = _load_yaml(args.output)
        except Exception as exc:
            sys.exit(f"❌  failed to read existing output file: {exc}")

    merged: OrderedDict[str, dict] = OrderedDict()

    # Keep all existing flags that still appear in new_flags
    for flag, old_entry in existing.items():
        if flag in new_flags:
            merged[flag] = old_entry

    # Add new flags that didn't previously exist
    for flag, new_entry in new_flags.items():
        if flag not in merged:
            merged[flag] = new_entry

    try:
        with args.output.open("w", encoding="utf-8") as fh:
            _dump_yaml(merged, fh)
    except Exception as exc:
        sys.exit(f"❌  could not write {args.output}: {exc}")

    print(f"✔  updated {args.output} with {len(merged):,} total flags "
          f"({len(new_flags):,} current, {len(existing):,} retained)")


if __name__ == "__main__":
    main()
