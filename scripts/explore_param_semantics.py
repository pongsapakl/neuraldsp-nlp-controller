"""Explore: what semantic signal lives in the full raw preset params?

Goals:
1. What params vary meaningfully across presets? (vs always-same)
2. Can we derive richer tone descriptions from raw params?
3. Can we auto-generate coverage anchors (replace hand-crafted pure anchors)?

Usage:
  uv run python scripts/explore_param_semantics.py
"""

import yaml
import numpy as np
from pathlib import Path
from collections import Counter, defaultdict

from pedalboard import load_plugin
from neuraldsp_nlp_controller.preset_loader import (
    parse_preset, discover_mapping, list_factory_presets, resolve_value
)

ANCHOR_PATH = Path(__file__).parent.parent / "data" / "anchors.yaml"

PLUGINS = [
    ("Archetype Tim Henson X",
     "/Library/Audio/Plug-Ins/VST3/Archetype Tim Henson X.vst3",
     "/Library/Audio/Presets/Neural DSP/Archetype Tim Henson X"),
]


def analyze_param_variance(plugin, preset_paths, key_map):
    """Analyze which params vary across presets and which are static."""
    all_values = defaultdict(list)

    for path in preset_paths:
        raw = parse_preset(str(path))
        for pk, pv in raw.items():
            pb_name = key_map.get(pk)
            if pb_name is None:
                continue
            resolved = resolve_value(pv, pb_name, plugin)
            if resolved is not None and isinstance(resolved, (int, float)) and not isinstance(resolved, bool):
                all_values[pb_name].append(float(resolved))

    # Compute variance stats
    stats = []
    for pb_name, values in all_values.items():
        arr = np.array(values)
        param = plugin.parameters[pb_name]
        mn, mx = float(param.min_value), float(param.max_value)
        rng = mx - mn if mx > mn else 1.0
        stats.append({
            "name": pb_name,
            "std": np.std(arr),
            "std_norm": np.std(arr) / rng,  # normalized by range
            "min": np.min(arr),
            "max": np.max(arr),
            "mean": np.mean(arr),
            "range": mx - mn,
            "n": len(values),
            "unique": len(set(values)),
        })

    return sorted(stats, key=lambda s: s["std_norm"], reverse=True)


def analyze_discrete_params(plugin, preset_paths, key_map):
    """Analyze enum/bool params and their distributions."""
    all_values = defaultdict(list)

    for path in preset_paths:
        raw = parse_preset(str(path))
        for pk, pv in raw.items():
            pb_name = key_map.get(pk)
            if pb_name is None:
                continue
            resolved = resolve_value(pv, pb_name, plugin)
            if resolved is not None and (isinstance(resolved, bool) or isinstance(resolved, str)):
                all_values[pb_name].append(resolved)

    results = {}
    for pb_name, values in all_values.items():
        counter = Counter(values)
        results[pb_name] = counter

    return results


def analyze_eq_curves(plugin, preset_paths, key_map):
    """Analyze EQ curve shapes across presets."""
    eq_bands = ["65_hz", "125_hz", "250_hz", "500_hz", "1_khz",
                "2_khz", "4_khz", "8_khz", "16_khz"]

    # Find EQ param names
    pb_params = set(plugin.parameters.keys())
    eq_prefixes = set()
    for p in pb_params:
        for band in eq_bands:
            if p.endswith(band):
                prefix = p[:-(len(band) + 1)]  # strip _65_hz
                eq_prefixes.add(prefix)

    curves = []
    for path in preset_paths:
        raw = parse_preset(str(path))
        for eq_prefix in eq_prefixes:
            curve = []
            for band in eq_bands:
                pb_name = f"{eq_prefix}_{band}"
                if pb_name not in pb_params:
                    continue
                # Find the preset key that maps to this
                for pk, mapped_pb in key_map.items():
                    if mapped_pb == pb_name:
                        if pk in raw:
                            val = resolve_value(raw[pk], pb_name, plugin)
                            if val is not None:
                                curve.append(float(val))
                            break

            if len(curve) == len(eq_bands):
                curves.append({
                    "preset": path.stem,
                    "eq_prefix": eq_prefix,
                    "curve": curve,
                })

    return curves


def classify_eq_shape(curve, center=50.0):
    """Classify an EQ curve shape into a semantic label."""
    arr = np.array(curve)
    bass = np.mean(arr[:3])  # 65-250 Hz
    mid = np.mean(arr[3:6])  # 500-2k Hz
    treble = np.mean(arr[6:])  # 4k-16k Hz
    deviation = np.std(arr)

    labels = []
    if deviation < 3:
        labels.append("flat")
    if bass > center + 5:
        labels.append("bass_boost")
    if bass < center - 5:
        labels.append("bass_cut")
    if mid < center - 5 and bass > center and treble > center:
        labels.append("mid_scoop")
    if mid > center + 5:
        labels.append("mid_push")
    if treble > center + 5:
        labels.append("treble_boost")
    if treble < center - 5:
        labels.append("treble_cut")
    if bass > center + 5 and treble > center + 5 and mid < center:
        labels.append("V_curve")
    if mid > center + 5 and bass < center and treble < center:
        labels.append("mid_hump")

    return labels if labels else ["neutral"]


def analyze_effect_combinations(preset_paths, key_map, plugin):
    """Analyze which effect combinations appear across presets."""
    # Find active params
    effect_active_params = {}
    for pb_name in plugin.parameters.keys():
        if pb_name.endswith("_active"):
            effect_active_params[pb_name] = pb_name

    combos = Counter()
    for path in preset_paths:
        raw = parse_preset(str(path))
        active = []
        for pk, mapped_pb in key_map.items():
            if mapped_pb in effect_active_params:
                if pk in raw:
                    val = resolve_value(raw[pk], mapped_pb, plugin)
                    if val is True:
                        # Clean up name
                        name = mapped_pb.replace("_active", "")
                        active.append(name)
        combo_key = tuple(sorted(active)) if active else ("none",)
        combos[combo_key] += 1

    return combos


def main():
    for plugin_name, vst3_path, preset_dir in PLUGINS:
        print(f"\n{'='*80}")
        print(f"ANALYZING: {plugin_name}")
        print(f"{'='*80}")

        plugin = load_plugin(vst3_path)
        presets = list_factory_presets(preset_dir)
        key_map = discover_mapping(plugin, presets[0])
        print(f"Presets: {len(presets)}, Mapped params: {len(key_map)}")

        # 1. Param variance
        print(f"\n--- TOP 30 MOST VARYING PARAMS (normalized std) ---")
        stats = analyze_param_variance(plugin, presets, key_map)
        for s in stats[:30]:
            print(f"  {s['name']:40s}  std_norm={s['std_norm']:.3f}  "
                  f"range=[{s['min']:.1f}-{s['max']:.1f}]  "
                  f"unique={s['unique']}/{s['n']}")

        print(f"\n--- BOTTOM 10 LEAST VARYING (near-constant) ---")
        for s in stats[-10:]:
            print(f"  {s['name']:40s}  std_norm={s['std_norm']:.3f}  "
                  f"mean={s['mean']:.1f}")

        # 2. Discrete params
        print(f"\n--- DISCRETE PARAM DISTRIBUTIONS ---")
        discrete = analyze_discrete_params(plugin, presets, key_map)
        for pb_name, counter in sorted(discrete.items()):
            if len(counter) > 1:  # only show if varies
                top3 = counter.most_common(3)
                dist = ", ".join(f"{v}:{c}" for v, c in top3)
                print(f"  {pb_name:40s}  {dist}")

        # 3. EQ curves
        print(f"\n--- EQ CURVE SHAPES ---")
        curves = analyze_eq_curves(plugin, presets, key_map)
        shape_counts = Counter()
        for c in curves:
            shapes = classify_eq_shape(c["curve"])
            for s in shapes:
                shape_counts[s] += 1
        for shape, count in shape_counts.most_common():
            print(f"  {shape:20s}  {count}")

        # Show a few examples
        print(f"\n  Sample curves:")
        for c in curves[:5]:
            shapes = classify_eq_shape(c["curve"])
            vals = [f"{v:.0f}" for v in c["curve"]]
            print(f"    {c['preset'][:25]:25s} [{', '.join(vals)}] → {shapes}")

        # 4. Effect combinations
        print(f"\n--- EFFECT COMBINATIONS ---")
        combos = analyze_effect_combinations(presets, key_map, plugin)
        for combo, count in combos.most_common(15):
            print(f"  {' + '.join(combo):50s}  {count} presets")

        # 5. Semantic dimensions we can auto-derive
        print(f"\n--- AUTO-DERIVABLE SEMANTIC DIMENSIONS ---")
        print("  From raw params, we can auto-generate these descriptors:")
        print("  1. Amp model → character (Roses=clean/Fender, Cherubs=crunch/Vox, Pink=lead/hi-gain)")
        print("  2. EQ shape → bass_boost, mid_scoop, V_curve, treble_bright, flat")
        print("  3. Gain level → clean headroom, edge of breakup, saturated, fully crushed")
        print("  4. Active effects → overdrive, compressor, chorus, delay, reverb")
        print("  5. Effect intensity → subtle/moderate/heavy (from mix/drive values)")
        print("  6. Cab/room → open vs closed cab, room on/off, room size")
        print("  7. EQ HPF/LPF → bass cut, treble cut, bandwidth")
        print("  8. Delay character → slapback (<200ms), rhythmic, ambient (>500ms)")
        print("  9. Reverb character → tight room, hall, cathedral")
        print("  10. Overall complexity → minimal (1 effect) vs heavily processed (4+)")

        # 6. Coverage gaps — what tonal regions are underserved?
        print(f"\n--- COVERAGE ANALYSIS ---")
        with open(ANCHOR_PATH) as f:
            anchors = yaml.safe_load(f)
        factory = [a for a in anchors if a.get("plugin_name") == plugin_name]

        # By amp character
        char_counts = Counter(a["tone"]["amp"]["character"] for a in factory)
        print(f"  By amp character: {dict(char_counts)}")

        # By gain level
        gain_buckets = {"very_low (<0.2)": 0, "low (0.2-0.4)": 0,
                        "moderate (0.4-0.6)": 0, "high (0.6-0.8)": 0,
                        "very_high (>0.8)": 0}
        for a in factory:
            g = a["tone"]["amp"]["gain"]
            if g < 0.2: gain_buckets["very_low (<0.2)"] += 1
            elif g < 0.4: gain_buckets["low (0.2-0.4)"] += 1
            elif g < 0.6: gain_buckets["moderate (0.4-0.6)"] += 1
            elif g < 0.8: gain_buckets["high (0.6-0.8)"] += 1
            else: gain_buckets["very_high (>0.8)"] += 1
        print(f"  By gain level: {gain_buckets}")

        # By active effects
        effect_counts = Counter()
        for a in factory:
            for eff in ["overdrive", "compressor", "chorus", "delay", "reverb"]:
                if a["tone"][eff]["active"]:
                    effect_counts[eff] += 1
        print(f"  Active effects across presets: {dict(effect_counts)}")

        # Combinations coverage
        combo_counts = Counter()
        for a in factory:
            active = []
            for eff in ["overdrive", "compressor", "chorus", "delay", "reverb"]:
                if a["tone"][eff]["active"]:
                    active.append(eff)
            combo_counts[tuple(sorted(active)) if active else ("none",)] += 1
        print(f"  Most common effect combos:")
        for combo, count in combo_counts.most_common(10):
            print(f"    {' + '.join(combo):40s}  {count}")


if __name__ == "__main__":
    main()
