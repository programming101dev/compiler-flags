#!/usr/bin/env python3
"""
update_category_map.py

Build / update a YAML mapping from GCC / Clang category headings
to your own canonical category names.

Each input compiler YAML looks like

    <category>:
      - -flag1
      - -flag2
      …

This script:

1.  Collects *all* category keys from the two compiler files.
2.  Loads --output (if it exists) – this is a YAML mapping
    {<compiler-category>: <your-canonical-name>}.
3.  For every compiler category that is **not** yet in the mapping,
    inserts it with value ``"change me"``.
4.  Writes the merged mapping back to --output
    (creating the file if necessary).

Existing keys (i.e. the ones you’ve already edited by hand)
are left untouched.

Order is preserved: all pre-existing keys stay where they were,
and new keys are appended in the order they are first found
(GCC first, then Clang).
"""

from __future__ import annotations

import argparse
import sys
import yaml
from pathlib import Path
from collections import OrderedDict
from yaml.representer import SafeRepresenter


# ──────────────────────────────────────────────────────────────────────────────
#  YAML helpers – always work with OrderedDict so key order round-trips
# ──────────────────────────────────────────────────────────────────────────────

class OrderedLoader(yaml.SafeLoader):                      # type: ignore[misc]
    """YAML loader that constructs mappings as OrderedDicts."""
    pass


def _construct_mapping(loader, node, deep=False):          # noqa: ANN001
    if not isinstance(node, yaml.MappingNode):
        raise yaml.constructor.ConstructorError(
            None, None,
            f"expected a mapping node, got {node.id}", node.start_mark
        )
    loader.flatten_mapping(node)
    return OrderedDict(loader.construct_pairs(node, deep))


OrderedLoader.add_constructor(                             # type: ignore[arg-type]
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)

# Make PyYAML able to *dump* an OrderedDict
yaml.add_representer(                                      # type: ignore[arg-type]
    OrderedDict,
    SafeRepresenter.represent_dict,
    Dumper=yaml.SafeDumper,
)


def load_ordered_yaml(path: Path) -> "OrderedDict[str, object]":
    """Load a YAML mapping (if the file exists) as an OrderedDict."""
    if not path.exists():
        return OrderedDict()
    with path.open(encoding="utf-8") as fh:
        data = yaml.load(fh, Loader=OrderedLoader)         # type: ignore[arg-type]
    if data is None:
        return OrderedDict()
    if not isinstance(data, OrderedDict):
        raise ValueError(f"{path} does not contain a top-level mapping")
    return data


def dump_ordered_yaml(obj: OrderedDict, path: Path) -> None:
    """Write *obj* (an OrderedDict) to *path* in block-style YAML."""
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(
            obj, fh,
            sort_keys=False,
            default_flow_style=False,
            allow_unicode=True,
        )


# ──────────────────────────────────────────────────────────────────────────────
#  Core logic
# ──────────────────────────────────────────────────────────────────────────────

def collect_categories(yaml_file: Path) -> list[str]:
    """
    Return the category keys from one compiler YAML, preserving file order.
    """
    data = load_ordered_yaml(yaml_file)
    return list(data.keys())


def update_mapping(
    gcc_categories: list[str],
    clang_categories: list[str],
    existing_map: "OrderedDict[str, str]",
) -> "OrderedDict[str, str]":
    """
    Return *existing_map* augmented with any new category keys.
    New keys are appended and given the value 'change me'.
    """
    # Ordered set of categories in the order we want to consider them
    ordered_seen: list[str] = []
    for cat in gcc_categories + clang_categories:
        if cat not in ordered_seen:
            ordered_seen.append(cat)

    # Build a fresh OrderedDict with existing keys first (in their order)
    updated: "OrderedDict[str, str]" = OrderedDict(existing_map)

    # Append any missing ones
    for cat in ordered_seen:
        if cat not in updated:
            updated[cat] = "change me"

    return updated


# ──────────────────────────────────────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Create / update a category-mapping YAML "
                    "for GCC and Clang flag category names."
    )
    ap.add_argument("--gcc", required=True, type=Path,
                    help="YAML produced by parse_gcc_options.py")
    ap.add_argument("--clang", required=True, type=Path,
                    help="YAML produced by parse-clang.py")
    ap.add_argument("--output", required=True, type=Path,
                    help="Mapping YAML to create or update")

    args = ap.parse_args()

    try:
        gcc_cats   = collect_categories(args.gcc)
        clang_cats = collect_categories(args.clang)
    except Exception as exc:                                # pragma: no cover
        sys.exit(f"❌  could not read input YAML: {exc}")

    existing_map = load_ordered_yaml(args.output)
    merged_map   = update_mapping(gcc_cats, clang_cats, existing_map)

    try:
        dump_ordered_yaml(merged_map, args.output)
    except Exception as exc:                                # pragma: no cover
        sys.exit(f"❌  could not write {args.output}: {exc}")

    new_entries = sum(1 for k in merged_map if k not in existing_map)
    print(f"✔  {len(merged_map):,} total categories "
          f"({new_entries} new) → {args.output}")


if __name__ == "__main__":
    main()
