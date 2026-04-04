"""Auto-discover and report preset → pedalboard parameter mapping.

Thin wrapper around preset_loader.discover_mapping() that prints a detailed
report. Useful for debugging mapping issues on new plugins.

Usage:
  uv run python scripts/auto_discover_mapping.py
  uv run python scripts/auto_discover_mapping.py /path/to/plugin.vst3 /path/to/presets/
"""

import sys
from pathlib import Path
from pedalboard import load_plugin

from neuraldsp_nlp_controller.preset_loader import (
    discover_mapping, list_factory_presets, load_preset, parse_preset,
)


def report_mapping(vst3_path: str, preset_dir: str):
    name = Path(vst3_path).stem
    print(f"\n{'='*60}")
    print(f"Auto-discovering: {name}")
    print(f"{'='*60}")

    plugin = load_plugin(vst3_path)
    print(f"Pedalboard params: {len(plugin.parameters)}")

    presets = list_factory_presets(preset_dir)
    if not presets:
        print("No preset files found!")
        return

    print(f"Factory presets: {len(presets)}")
    sample = presets[0]
    print(f"Analyzing: {sample.name}\n")

    key_map = discover_mapping(plugin, sample)
    preset_params = parse_preset(str(sample))

    # Mapped keys
    print(f"MAPPED: {len(key_map)} / {len(preset_params)} preset keys")
    for pk, pb in sorted(key_map.items()):
        print(f"  {pk} → {pb}")

    # Unmapped keys
    unmapped = [k for k in preset_params if k not in key_map]
    if unmapped:
        print(f"\nUNMAPPED ({len(unmapped)}):")
        for k in sorted(unmapped):
            print(f"  ? {k} = {preset_params[k]}")
    else:
        print("\n✓ All preset keys mapped!")

    # Apply across all presets
    print(f"\n--- Apply test across ALL {len(presets)} presets ---")
    total_a, total_f, total_s = 0, 0, 0
    for pf in presets:
        plugin = load_plugin(vst3_path)
        result = load_preset(plugin, pf, key_map)
        total_a += result['applied']
        total_f += result['failed']
        total_s += result['skipped']
    actionable = total_a + total_f
    pct = 100 * total_a / actionable if actionable else 0
    print(f"Applied: {total_a}/{actionable} ({pct:.1f}%)")
    print(f"Failed:  {total_f}")
    print(f"Skipped: {total_s} (no mapping)")


def main():
    if len(sys.argv) >= 3:
        plugins = [(sys.argv[1], sys.argv[2])]
    else:
        plugins = [
            ("/Library/Audio/Plug-Ins/VST3/Archetype Tim Henson X.vst3",
             "/Library/Audio/Presets/Neural DSP/Archetype Tim Henson X"),
            ("/Library/Audio/Plug-Ins/VST3/Archetype Cory Wong X.vst3",
             "/Library/Audio/Presets/Neural DSP/Archetype Cory Wong X"),
        ]

    for vst3_path, preset_dir in plugins:
        if not Path(vst3_path).exists():
            print(f"\nSkipping {Path(vst3_path).stem} — not installed")
            continue
        report_mapping(vst3_path, preset_dir)


if __name__ == "__main__":
    main()
