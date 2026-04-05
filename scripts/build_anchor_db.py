"""Build anchor database from all installed Neural DSP plugins.

Pipeline:
  1. Build preset anchors from factory presets (honest canonical descriptions)
  2. Save to data/anchors.yaml

Usage:
  uv run python scripts/build_anchor_db.py
"""

import time
from pathlib import Path

from neuraldsp_nlp_controller.anchor_builder import build_anchors, save_anchors

ANCHOR_PATH = Path(__file__).parent.parent / "data" / "anchors.yaml"


def main():
    print("Building anchor database from factory presets...")
    start = time.time()

    anchors = build_anchors()
    elapsed = time.time() - start
    print(f"\nBuilt {len(anchors)} preset anchors in {elapsed:.1f}s\n")

    # Show sample descriptions
    print("Sample descriptions:")
    for a in anchors[:5]:
        print(f"  [{a['plugin_name'][:15]}] {a['description'][:120]}")
    print("  ...")
    for a in anchors[-3:]:
        print(f"  [{a['plugin_name'][:15]}] {a['description'][:120]}")

    # Stats per plugin
    plugins = set(a['plugin_name'] for a in anchors if a['plugin_name'])
    for p in plugins:
        count = sum(1 for a in anchors if a['plugin_name'] == p)
        print(f"\n{p}: {count} anchors")

    # Character distribution
    chars = {}
    for a in anchors:
        c = a['tone']['amp']['character']
        chars[c] = chars.get(c, 0) + 1
    print(f"\nCharacter distribution: {chars}")

    save_anchors(anchors, ANCHOR_PATH)
    print(f"\nSaved to {ANCHOR_PATH}")


if __name__ == "__main__":
    main()
