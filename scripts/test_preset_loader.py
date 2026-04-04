"""Test preset loader against all factory presets for both plugins.

Usage:
  uv run python scripts/test_preset_loader.py
"""

from pathlib import Path
from pedalboard import load_plugin

from neuraldsp_nlp_controller.preset_loader import (
    discover_mapping, list_factory_presets, load_preset,
)

PLUGINS = [
    ("/Library/Audio/Plug-Ins/VST3/Archetype Tim Henson X.vst3",
     "/Library/Audio/Presets/Neural DSP/Archetype Tim Henson X"),
    ("/Library/Audio/Plug-Ins/VST3/Archetype Cory Wong X.vst3",
     "/Library/Audio/Presets/Neural DSP/Archetype Cory Wong X"),
]


def test_plugin(vst3_path: str, preset_dir: str):
    name = Path(vst3_path).stem
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"{'='*60}")

    plugin = load_plugin(vst3_path)
    print(f"Loaded. {len(plugin.parameters)} pedalboard params.")

    presets = list_factory_presets(preset_dir)
    print(f"Factory presets: {len(presets)}")

    if not presets:
        print("No presets found!")
        return 0.0

    # Discover mapping from first preset
    key_map = discover_mapping(plugin, presets[0])
    print(f"Mapped keys: {len(key_map)}\n")

    total_applied, total_failed, total_skipped = 0, 0, 0
    all_errors: list[str] = []

    for preset_path in presets:
        # Reload plugin defaults before each preset
        plugin = load_plugin(vst3_path)

        result = load_preset(plugin, preset_path, key_map)
        a, f, s = result['applied'], result['failed'], result['skipped']
        actionable = a + f
        pct = 100 * a / actionable if actionable else 0
        status = "✓" if f == 0 else "!"
        line = f"  {status} {preset_path.stem}: {a}/{actionable} ({pct:.0f}%)"
        if f > 0:
            line += f" — {f} failed"
        print(line)

        total_applied += a
        total_failed += f
        total_skipped += s
        all_errors.extend(result['errors'])

    # Summary
    total_actionable = total_applied + total_failed
    pct = 100 * total_applied / total_actionable if total_actionable else 0
    print(f"\n--- {name} SUMMARY ---")
    print(f"Presets tested:  {len(presets)}")
    print(f"Total params:    {total_actionable} actionable ({total_skipped} skipped)")
    print(f"Applied:         {total_applied}/{total_actionable} ({pct:.1f}%)")
    print(f"Failed:          {total_failed}")

    if all_errors:
        print(f"\nErrors (first 10):")
        for err in all_errors[:10]:
            print(f"  - {err}")

    return pct


def main():
    results = {}
    for vst3_path, preset_dir in PLUGINS:
        if not Path(vst3_path).exists():
            print(f"\nSkipping {Path(vst3_path).stem} — not installed")
            continue
        results[Path(vst3_path).stem] = test_plugin(vst3_path, preset_dir)

    print(f"\n{'='*60}")
    print("OVERALL RESULTS")
    print(f"{'='*60}")
    for name, pct in results.items():
        status = "✓ PASS" if pct >= 95 else "! NEEDS WORK"
        print(f"  {name}: {pct:.1f}% — {status}")


if __name__ == "__main__":
    main()
