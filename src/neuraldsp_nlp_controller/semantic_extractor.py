"""Auto-extract semantic tags from raw preset parameters.

Reads all ~170 raw params from a factory preset and produces human-readable
tonal descriptors. No ML — pure rule-based extraction using param names,
discrete values, and continuous value ranges.

Plugin-specific knowledge is isolated in _PLUGIN_SEMANTICS config dicts.
The extraction logic itself is generic.

Usage:
    tags = extract_semantic_tags(plugin, preset_path, key_map)
    # → ["Fender-style clean", "glassy", "moderate gain", "light compression",
    #    "modern delay", "clean repeats", "lush hall reverb", ...]
"""

import re
from pathlib import Path

from .preset_loader import parse_preset, resolve_value


# ── Plugin-specific semantic config ──────────────────────────────────

_PLUGIN_SEMANTICS = {
    "Archetype Tim Henson X": {
        "amp_types": {
            "Roses":   {"character": "clean",  "tags": ["Fender-style clean", "glassy", "bell-like"]},
            "Cherubs": {"character": "crunch", "tags": ["Vox-style crunch", "chimey", "British"]},
            "Pink":    {"character": "lead",   "tags": ["hi-gain lead", "saturated", "modern high-gain"]},
        },
        "amp_gain_param": {
            "Roses":   "roses_amp_gain",
            "Cherubs": "cherubs_amp_gain",
            "Pink":    "pink_amp_gain",
        },
        "amp_prefix": {
            "Roses":   "roses_amp",
            "Cherubs": "cherubs_amp",
            "Pink":    "pink_amp",
        },
        "eq_prefix": {
            "Roses":   "roses_eq",
            "Cherubs": "cherubs_eq",
            "Pink":    "pink_eq",
        },
        "delay_types": {
            "Modern":          ["modern delay", "clean repeats"],
            "Diffusion":       ["diffused delay", "washy echoes", "textured"],
            "Vintage Digital": ["vintage delay", "lo-fi repeats", "retro"],
        },
        "reverb_modes": {
            "Reverb":  ["reverb"],
            "Shimmer": ["shimmer reverb", "ethereal", "pad-like"],
        },
        "mic_semantics": {
            "Dynamic 57":    ["dynamic mic punch", "present mids"],
            "Dynamic 421":   ["dynamic mic clarity", "balanced"],
            "Ribbon 121":    ["ribbon mic warmth", "smooth treble"],
            "Ribbon 160":    ["ribbon mic darkness", "thick tone"],
            "Condenser 414": ["condenser clarity", "detailed highs", "airy"],
        },
    },
    "Archetype Cory Wong X": {
        "amp_types": {
            "Funk":  {"character": "clean",  "tags": ["funky clean", "tight", "percussive"]},
            "Clean": {"character": "clean",  "tags": ["pristine clean", "transparent", "hi-fi"]},
            "Snob":  {"character": "crunch", "tags": ["boutique crunch", "touch-sensitive", "vintage"]},
        },
        "amp_gain_param": {
            "Funk":  "d_i_funk_console_gain",
            "Clean": "the_clean_machine_gain",
            "Snob":  "the_amp_snob_gain",
        },
        "amp_prefix": {
            "Funk":  "d_i_funk_console",
            "Clean": "the_clean_machine",
            "Snob":  "the_amp_snob",
        },
        "eq_prefix": {
            "Funk":  "d_i_funk_console_eq",
            "Clean": "the_clean_machine_eq",
            "Snob":  "the_amp_snob_eq",
        },
        "delay_types": {
            "Modern":          ["modern delay", "clean repeats"],
            "Diffusion":       ["diffused delay", "washy echoes"],
            "Vintage Digital": ["vintage delay", "lo-fi repeats"],
        },
        "reverb_modes": {
            "Reverb":  ["reverb"],
            "Shimmer": ["shimmer reverb", "ethereal"],
        },
        "mic_semantics": {
            "Dynamic 57":    ["dynamic mic punch"],
            "Dynamic 421":   ["dynamic mic clarity"],
            "Ribbon 121":    ["ribbon mic warmth"],
            "Ribbon 160":    ["ribbon mic darkness"],
            "Condenser 414": ["condenser clarity", "airy"],
        },
    },
}

# ── EQ band names (Neural DSP 9-band standard) ──────────────────────

_EQ_BANDS = ["65_hz", "125_hz", "250_hz", "500_hz", "1_khz",
             "2_khz", "4_khz", "8_khz", "16_khz"]


# ── Generic extraction helpers ───────────────────────────────────────

def _read_raw(plugin, pb_name: str):
    """Read a raw param value from the plugin."""
    try:
        return getattr(plugin, pb_name)
    except (AttributeError, Exception):
        return None


def _read_resolved(plugin, preset_data: dict, key_map: dict, pb_name: str):
    """Read a resolved value from preset data for a given pedalboard param."""
    for pk, mapped in key_map.items():
        if mapped == pb_name and pk in preset_data:
            return resolve_value(preset_data[pk], pb_name, plugin)
    return None


def _gain_tags(gain_val: float, param_range: tuple[float, float]) -> list[str]:
    """Generate gain-level tags from a normalized 0-1 value."""
    mn, mx = param_range
    rng = mx - mn if mx > mn else 1.0
    norm = (gain_val - mn) / rng

    if norm < 0.15:
        return ["very low gain", "clean headroom"]
    elif norm < 0.35:
        return ["low gain", "gentle warmth"]
    elif norm < 0.55:
        return ["moderate gain"]
    elif norm < 0.75:
        return ["high gain", "saturated"]
    else:
        return ["very high gain", "fully saturated", "crushing"]


def _classify_eq_shape(curve: list[float], center: float = 0.0) -> list[str]:
    """Classify an EQ curve shape into semantic labels.

    Expects values as deviations from center (dB offsets).
    """
    if len(curve) < 6:
        return []

    bass = sum(curve[:3]) / 3    # 65-250 Hz
    mid = sum(curve[3:6]) / 3    # 500-2k Hz
    treble = sum(curve[6:]) / max(1, len(curve) - 6)  # 4k-16k Hz
    deviation = max(abs(v - center) for v in curve)

    labels = []
    if deviation < 1.5:
        return ["flat EQ"]

    if bass > center + 2:
        labels.append("bass boost")
    if bass < center - 2:
        labels.append("bass cut")
    if mid < center - 2 and bass > center and treble > center:
        labels.append("mid-scoop")
    if mid > center + 2:
        labels.append("mid-forward")
    if treble > center + 2:
        labels.append("bright")
    if treble < center - 2:
        labels.append("dark")
    if bass > center + 2 and treble > center + 2 and mid < center:
        labels.append("V-curve")
    if mid > center + 2 and bass < center and treble < center:
        labels.append("mid-hump")

    return labels if labels else ["neutral EQ"]


def _overdrive_tags(active: bool, drive: float | None, tone: float | None,
                    level: float | None) -> list[str]:
    """Generate overdrive-specific tags."""
    if not active:
        return []

    tags = []
    if drive is not None:
        if drive < 25:
            tags.append("light overdrive boost")
        elif drive < 50:
            tags.append("moderate overdrive")
        elif drive < 75:
            tags.append("heavy overdrive")
        else:
            tags.append("maxed overdrive", )
            tags.append("extreme saturation")

    if tone is not None:
        if tone < 30:
            tags.append("dark drive")
        elif tone > 70:
            tags.append("bright drive")

    return tags if tags else ["overdrive"]


def _compressor_tags(active: bool, compression: float | None,
                     attack: str | None) -> list[str]:
    """Generate compressor-specific tags."""
    if not active:
        return []

    tags = []
    if compression is not None:
        if compression < 30:
            tags.append("gentle compression")
        elif compression < 60:
            tags.append("moderate compression")
        else:
            tags.append("heavy compression")
            tags.append("squashed")

    if attack is not None:
        if attack == "Fast":
            tags.append("fast attack")
        elif attack == "Slow":
            tags.append("slow attack")

    return tags if tags else ["compressed"]


def _delay_tags(active: bool, time_ms: float | None, feedback: float | None,
                mix: float | None) -> list[str]:
    """Generate delay character tags from raw params."""
    if not active:
        return []

    tags = []
    if time_ms is not None:
        if time_ms < 100:
            tags.append("slapback delay")
        elif time_ms < 300:
            tags.append("short delay")
        elif time_ms < 600:
            tags.append("rhythmic delay")
        else:
            tags.append("long delay")
            tags.append("ambient echoes")

    if feedback is not None:
        if feedback > 70:
            tags.append("self-oscillating")
        elif feedback > 50:
            tags.append("long decay repeats")

    if mix is not None:
        if mix < 15:
            tags.append("subtle delay")
        elif mix > 50:
            tags.append("prominent delay")
            tags.append("wash of echoes")

    return tags if tags else ["delay"]


def _reverb_tags(active: bool, decay: float | None, mix: float | None,
                 high_cut: float | None) -> list[str]:
    """Generate reverb character tags from raw params."""
    if not active:
        return []

    tags = []
    if decay is not None:
        if decay < 25:
            tags.append("tight room")
        elif decay < 50:
            tags.append("medium room")
        elif decay < 75:
            tags.append("hall reverb")
        else:
            tags.append("cathedral reverb")
            tags.append("cavernous")

    if mix is not None:
        if mix < 15:
            tags.append("subtle reverb")
        elif mix > 50:
            tags.append("lush reverb")
            tags.append("spacious")

    if high_cut is not None and high_cut < 40:
        tags.append("dark reverb")

    return tags if tags else ["reverb"]


def _complexity_tags(active_effects: list[str]) -> list[str]:
    """Describe overall signal chain complexity."""
    n = len(active_effects)
    if n == 0:
        return ["dry", "minimal processing"]
    elif n == 1:
        return ["simple"]
    elif n <= 3:
        return ["moderately processed"]
    else:
        return ["heavily layered", "complex signal chain"]


# ── Main extraction function ─────────────────────────────────────────

def extract_semantic_tags(plugin, preset_path: str | Path,
                          key_map: dict[str, str]) -> list[str]:
    """Extract semantic tags from raw preset parameters.

    Reads the full ~170 params and derives human-readable tonal descriptors.
    Returns a deduplicated list of tags.

    Args:
        plugin: A pedalboard-loaded VST3Plugin with the preset already loaded.
        preset_path: Path to the factory preset (for reading raw values).
        key_map: Mapping from preset keys to pedalboard param names.
    """
    plugin_name = getattr(plugin, 'name', '')
    semantics = _PLUGIN_SEMANTICS.get(plugin_name, {})

    # Parse raw preset data
    preset_data = parse_preset(str(preset_path))
    tags: list[str] = []

    # 1. Amp character from amp_type
    amp_type_val = _read_raw(plugin, "amp_type")
    amp_types = semantics.get("amp_types", {})
    if amp_type_val and amp_type_val in amp_types:
        tags.extend(amp_types[amp_type_val]["tags"])

    # 2. Gain staging from active amp's gain param
    gain_params = semantics.get("amp_gain_param", {})
    if amp_type_val and amp_type_val in gain_params:
        gain_pb = gain_params[amp_type_val]
        gain_val = _read_raw(plugin, gain_pb)
        if gain_val is not None and gain_pb in plugin.parameters:
            param = plugin.parameters[gain_pb]
            tags.extend(_gain_tags(float(gain_val),
                                   (float(param.min_value), float(param.max_value))))

    # 3. EQ shape from active amp's EQ bands
    eq_prefixes = semantics.get("eq_prefix", {})
    if amp_type_val and amp_type_val in eq_prefixes:
        eq_pfx = eq_prefixes[amp_type_val]
        curve = []
        for band in _EQ_BANDS:
            pb_name = f"{eq_pfx}_{band}"
            val = _read_raw(plugin, pb_name)
            if val is not None:
                curve.append(float(val))
        if len(curve) >= 6:
            tags.extend(_classify_eq_shape(curve))

    # 4. Overdrive
    od_active = _read_raw(plugin, "overdrive_active")
    od_drive = _read_raw(plugin, "overdrive_drive")
    od_tone = _read_raw(plugin, "overdrive_tone")
    od_level = _read_raw(plugin, "overdrive_level")
    tags.extend(_overdrive_tags(
        bool(od_active) if od_active is not None else False,
        float(od_drive) if od_drive is not None else None,
        float(od_tone) if od_tone is not None else None,
        float(od_level) if od_level is not None else None,
    ))

    # 5. Compressor
    comp_active = _read_raw(plugin, "compressor_active")
    comp_compression = _read_raw(plugin, "compressor_compression")
    comp_attack = _read_raw(plugin, "compressor_attack")
    tags.extend(_compressor_tags(
        bool(comp_active) if comp_active is not None else False,
        float(comp_compression) if comp_compression is not None else None,
        str(comp_attack) if comp_attack is not None else None,
    ))

    # 6. Delay — type-specific tags + character tags
    delay_active = _read_raw(plugin, "delay_active")
    if delay_active:
        delay_type = _read_raw(plugin, "delay_type")
        delay_types = semantics.get("delay_types", {})
        if delay_type and str(delay_type) in delay_types:
            tags.extend(delay_types[str(delay_type)])

        delay_time = _read_raw(plugin, "delay_time")
        delay_feedback = _read_raw(plugin, "delay_feedback")
        delay_mix = _read_raw(plugin, "delay_mix")
        tags.extend(_delay_tags(
            True,
            float(delay_time) if delay_time is not None else None,
            float(delay_feedback) if delay_feedback is not None else None,
            float(delay_mix) if delay_mix is not None else None,
        ))

        # Delay mode (stereo width)
        delay_mode = _read_raw(plugin, "delay_mode")
        if delay_mode:
            mode_str = str(delay_mode)
            if mode_str == "Wide":
                tags.append("wide stereo delay")
            elif mode_str == "PingPong":
                tags.append("ping-pong delay")

    # 7. Reverb — mode-specific tags + character tags
    reverb_active = _read_raw(plugin, "reverb_active")
    if reverb_active:
        reverb_shimmer = _read_raw(plugin, "reverb_shimmer")
        reverb_modes = semantics.get("reverb_modes", {})
        if reverb_shimmer and str(reverb_shimmer) in reverb_modes:
            tags.extend(reverb_modes[str(reverb_shimmer)])

        reverb_decay = _read_raw(plugin, "reverb_decay")
        reverb_mix = _read_raw(plugin, "reverb_mix")
        reverb_high_cut = _read_raw(plugin, "reverb_high_cut")
        tags.extend(_reverb_tags(
            True,
            float(reverb_decay) if reverb_decay is not None else None,
            float(reverb_mix) if reverb_mix is not None else None,
            float(reverb_high_cut) if reverb_high_cut is not None else None,
        ))

    # 8. Cab/mic character — from left mic (primary)
    amp_prefixes = semantics.get("amp_prefix", {})
    mic_semantics = semantics.get("mic_semantics", {})
    if amp_type_val and amp_type_val in amp_prefixes:
        amp_pfx = amp_prefixes[amp_type_val]
        mic_l = _read_raw(plugin, f"{amp_pfx}_cab_mic_l_type")
        if mic_l and str(mic_l) in mic_semantics:
            tags.extend(mic_semantics[str(mic_l)])

    # 9. Boost pedal
    boost_active = _read_raw(plugin, "boost_active")
    if boost_active:
        boost_gain = _read_raw(plugin, "boost_gain")
        if boost_gain is not None and float(boost_gain) > 60:
            tags.append("hot boost")
        else:
            tags.append("clean boost")

    # 10. Overall complexity
    active_effects = []
    for eff, param in [("overdrive", "overdrive_active"),
                       ("compressor", "compressor_active"),
                       ("delay", "delay_active"),
                       ("reverb", "reverb_active"),
                       ("boost", "boost_active")]:
        val = _read_raw(plugin, param)
        if val:
            active_effects.append(eff)
    tags.extend(_complexity_tags(active_effects))

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for t in tags:
        t_lower = t.lower()
        if t_lower not in seen:
            seen.add(t_lower)
            unique.append(t)

    return unique
