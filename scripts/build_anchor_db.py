"""Build anchor database from all installed Neural DSP plugins.

Full pipeline:
  1. Build factory anchors with rich semantic descriptions (from raw params)
  2. Add systematic coverage anchors (replace hand-crafted pure effect anchors)
  3. Save to data/anchors.yaml

Usage:
  uv run python scripts/build_anchor_db.py
"""

import time
from pathlib import Path

from neuraldsp_nlp_controller.anchor_builder import build_anchors, save_anchors

# Import inline to avoid circular issues if run standalone
import sys
sys.path.insert(0, str(Path(__file__).parent))
from generate_coverage_anchors import add_coverage_anchors

ANCHOR_PATH = Path(__file__).parent.parent / "data" / "anchors.yaml"


def main():
    print("Building anchor database from factory presets...")
    start = time.time()

    # Step 1: Build factory anchors with semantic descriptions
    anchors = build_anchors()
    n_factory = len(anchors)
    elapsed_factory = time.time() - start
    print(f"\nBuilt {n_factory} factory anchors in {elapsed_factory:.1f}s")

    # Step 2: Add coverage anchors
    anchors = add_coverage_anchors(anchors)
    n_coverage = len(anchors) - n_factory
    print(f"Added {n_coverage} coverage anchors")

    elapsed = time.time() - start
    print(f"Total: {len(anchors)} anchors in {elapsed:.1f}s\n")

    # Show sample descriptions (old vs new style)
    print("Sample descriptions:")
    for a in anchors[:5]:
        print(f"  [{a['plugin_name'][:15]}] {a['description'][:120]}")
    print(f"  ...")
    for a in anchors[-3:]:
        pname = a['plugin_name'][:15] if a['plugin_name'] else 'Coverage'
        print(f"  [{pname}] {a['description'][:120]}")

    # Stats
    plugins = set(a['plugin_name'] for a in anchors if a['plugin_name'])
    for p in plugins:
        count = sum(1 for a in anchors if a['plugin_name'] == p)
        print(f"\n{p}: {count} anchors")

    # Show character distribution
    chars = {}
    for a in anchors:
        c = a['tone']['amp']['character']
        chars[c] = chars.get(c, 0) + 1
    print(f"\nCharacter distribution: {chars}")

    # Save
    save_anchors(anchors, ANCHOR_PATH)
    print(f"\nSaved to {ANCHOR_PATH}")


if __name__ == "__main__":
    main()
