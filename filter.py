#!/usr/bin/env python3
"""
filter_flags.py

Read a merged YAML file and write a filtered YAML file that retains only those
flags where "include" is true.

Validation:
- Every entry must have an "include" field (true or false)
- If "has_arg" is true and "include" is true, it must also have a "use_arg" field

Usage:
    filter_flags.py --input merged.yaml --output final.yaml
"""

from __future__ import annotations

import argparse
import sys
import yaml
from pathlib import Path
from collections import OrderedDict


# ──────────────────────────────────────────────────────────────────────────────
#  YAML helpers – preserve mapping order on load and dump
# ──────────────────────────────────────────────────────────────────────────────
class _OrderedLoader(yaml.SafeLoader): pass
class _OrderedDumper(yaml.SafeDumper): pass

def _construct_mapping(loader: _OrderedLoader, node, deep=False):
    if not isinstance(node, yaml.MappingNode):
        raise yaml.constructor.ConstructorError(
            None, None, f"expected a mapping node, got {node.id}", node.start_mark
        )
    loader.flatten_mapping(node)
    return OrderedDict(loader.construct_pairs(node, deep))

def _represent_ordered_dict(dumper: _OrderedDumper, data: OrderedDict):
    return dumper.represent_mapping(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, data.items())

_OrderedLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)
_OrderedDumper.add_representer(OrderedDict, _represent_ordered_dict)


def _load_yaml(path: Path) -> OrderedDict[str, dict]:
    with path.open(encoding="utf-8") as fh:
        data = yaml.load(fh, Loader=_OrderedLoader)
    if not isinstance(data, OrderedDict):
        raise ValueError(f"{path} does not contain a top-level mapping")
    return data


def _dump_yaml(obj: OrderedDict[str, dict], path: Path) -> None:
    with path.open("w", encoding="utf-8") as fh:
        yaml.dump(
            obj,
            fh,
            Dumper=_OrderedDumper,
            sort_keys=False,
            default_flow_style=False,
            allow_unicode=True,
        )


# ──────────────────────────────────────────────────────────────────────────────
#  Validation & Filtering
# ──────────────────────────────────────────────────────────────────────────────
def _validate_and_filter(
    all_flags: OrderedDict[str, dict]
) -> OrderedDict[str, dict]:
    filtered: OrderedDict[str, dict] = OrderedDict()

    for flag, info in all_flags.items():
        if "include" not in info:
            formatted = yaml.dump({flag: info}, Dumper=_OrderedDumper, sort_keys=False)
            sys.exit(f"❌  flag {flag!r} is missing required field: include\n\n{formatted.strip()}")

        include = info["include"]
        has_arg = info.get("has_arg", False)

        if include and has_arg and "use_arg" not in info:
            formatted = yaml.dump({flag: info}, Dumper=_OrderedDumper, sort_keys=False)
            sys.exit(f"❌  flag {flag!r} has_arg=true and include=true but is missing use_arg\n\n{formatted.strip()}")

        if include:
            clean_info = info.copy()
            clean_info.pop("include", None)
            filtered[flag] = clean_info

    return filtered


# ──────────────────────────────────────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(
        description="Filter merged flag list to only those with include=true, with validation."
    )
    ap.add_argument("--input", required=True, type=Path, help="Merged YAML file with flag entries")
    ap.add_argument("--output", required=True, type=Path, help="Destination YAML output file")
    args = ap.parse_args()

    try:
        all_flags = _load_yaml(args.input)
    except Exception as exc:
        sys.exit(f"❌  failed to load {args.input}: {exc}")

    filtered_flags = _validate_and_filter(all_flags)

    try:
        _dump_yaml(filtered_flags, args.output)
    except Exception as exc:
        sys.exit(f"❌  could not write {args.output}: {exc}")

    print(f"✔  wrote {len(filtered_flags):,} included flags → {args.output}")


if __name__ == "__main__":
    main()
