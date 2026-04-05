"""Auto-generate coverage anchors to fill semantic gaps in the anchor DB.

Replaces the hand-crafted add_pure_effect_anchors.py with a systematic
approach that generates anchors for every semantic dimension:
- Per amp type: clean + driven variants
- Per effect: subtle + heavy variants
- Per delay/reverb type: dedicated anchors
- Common combinations: OD+delay, compression+reverb, etc.
- Genre anchors: blues, metal, jazz, ambient, etc.

Re-runnable: removes previous [Coverage] anchors before adding.

Usage:
  uv run python scripts/generate_coverage_anchors.py
  # Or called from build_anchor_db.py as part of the full pipeline
"""

import yaml
from pathlib import Path

from neuraldsp_nlp_controller.semantic_extractor import _PLUGIN_SEMANTICS

ANCHOR_PATH = Path(__file__).parent.parent / "data" / "anchors.yaml"

# ── Neutral baseline ─────────────────────────────────────────────────

_NEUTRAL_AMP = {
    "character": "clean", "gain": 0.4, "bass": 0.5, "mid": 0.5,
    "treble": 0.5, "presence": 0.5, "master": 0.5, "output": 0.5,
}
_OFF = {
    "overdrive":  {"active": False, "drive": 0.5, "tone": 0.5, "level": 0.5},
    "compressor": {"active": False, "attack": 0.5, "release": 0.5, "compression": 0.5},
    "chorus":     {"active": False, "rate": 0.5, "depth": 0.5, "mix": 0.5},
    "delay":      {"active": False, "time": 0.5, "feedback": 0.5, "mix": 0.5},
    "reverb":     {"active": False, "size": 0.5, "damping": 0.5, "mix": 0.5},
}


def _make(description: str, **overrides) -> dict:
    """Create a coverage anchor with neutral base + overrides."""
    tone = {k: dict(v) for k, v in _OFF.items()}
    tone["amp"] = dict(_NEUTRAL_AMP)
    for key, val in overrides.items():
        section, param = key.split(".", 1)
        tone[section][param] = val
    return {
        "description": description,
        "tone": tone,
        "plugin_name": "",
        "preset_name": f"[Coverage] {description.split(',')[0]}",
        "preset_path": "",
    }


def generate_coverage_anchors() -> list[dict]:
    """Generate systematic coverage anchors for all semantic dimensions."""
    anchors = []

    # ── 1. Amp character anchors ─────────────────────────────────────
    # Per-plugin amp types with their semantic flavor
    for plugin_name, semantics in _PLUGIN_SEMANTICS.items():
        for amp_val, info in semantics.get("amp_types", {}).items():
            char = info["character"]
            tags = info["tags"]
            tag_str = ", ".join(tags)

            # Clean variant
            anchors.append(_make(
                f"{tag_str}, clean, low gain, no effects, pure amp tone",
                **{"amp.character": char, "amp.gain": 0.25},
            ))
            # Driven variant
            if char in ("crunch", "lead"):
                anchors.append(_make(
                    f"{tag_str}, pushed hard, high gain, aggressive",
                    **{"amp.character": char, "amp.gain": 0.8},
                ))

    # ── 2. Overdrive anchors ─────────────────────────────────────────
    anchors.append(_make(
        "overdrive, light drive boost, edge of breakup, warm push, transparent",
        **{"overdrive.active": True, "overdrive.drive": 0.25, "overdrive.tone": 0.5, "overdrive.level": 0.6},
    ))
    anchors.append(_make(
        "overdrive, heavy drive, crunchy saturation, tube screamer, thick distortion",
        **{"overdrive.active": True, "overdrive.drive": 0.7, "overdrive.tone": 0.6, "overdrive.level": 0.7},
    ))
    anchors.append(_make(
        "overdrive, bright cutting drive, treble boost, bite",
        **{"overdrive.active": True, "overdrive.drive": 0.5, "overdrive.tone": 0.85, "overdrive.level": 0.65},
    ))
    anchors.append(_make(
        "overdrive, dark warm drive, rolled off highs, smooth saturation",
        **{"overdrive.active": True, "overdrive.drive": 0.5, "overdrive.tone": 0.2, "overdrive.level": 0.65},
    ))

    # ── 3. Compressor anchors ────────────────────────────────────────
    anchors.append(_make(
        "compressor, light compression, subtle squeeze, even dynamics, transparent",
        **{"compressor.active": True, "compressor.compression": 0.25, "compressor.attack": 0.4},
    ))
    anchors.append(_make(
        "compressor, heavy compression, squashed, sustained, studio squeeze, punchy",
        **{"compressor.active": True, "compressor.compression": 0.8, "compressor.attack": 0.6},
    ))

    # ── 4. Chorus anchors ────────────────────────────────────────────
    anchors.append(_make(
        "chorus, subtle shimmer, light modulation, clean width, sparkle",
        **{"chorus.active": True, "chorus.rate": 0.3, "chorus.depth": 0.3, "chorus.mix": 0.3},
    ))
    anchors.append(_make(
        "chorus, lush 80s chorus, thick modulation, wide stereo, detuned, JC-120",
        **{"chorus.active": True, "chorus.rate": 0.4, "chorus.depth": 0.7, "chorus.mix": 0.6},
    ))

    # ── 5. Delay anchors (per type + per character) ──────────────────
    # Character-based (universal)
    anchors.append(_make(
        "delay, slapback echo, rockabilly, short repeat, slap",
        **{"delay.active": True, "delay.time": 0.1, "delay.feedback": 0.15, "delay.mix": 0.4},
    ))
    anchors.append(_make(
        "delay, rhythmic delay, dotted eighth, the edge, U2 style",
        **{"delay.active": True, "delay.time": 0.45, "delay.feedback": 0.35, "delay.mix": 0.35},
    ))
    anchors.append(_make(
        "delay, long ambient echo, spacious, atmospheric, trailing repeats",
        **{"delay.active": True, "delay.time": 0.65, "delay.feedback": 0.5, "delay.mix": 0.4},
    ))

    # Type-specific (from plugin semantics)
    all_delay_types = set()
    for semantics in _PLUGIN_SEMANTICS.values():
        for dtype, dtags in semantics.get("delay_types", {}).items():
            if dtype not in all_delay_types:
                all_delay_types.add(dtype)
                anchors.append(_make(
                    f"delay, {', '.join(dtags)}, medium tempo",
                    **{"delay.active": True, "delay.time": 0.4, "delay.feedback": 0.35, "delay.mix": 0.35},
                ))

    # ── 6. Reverb anchors (per mode + per size) ──────────────────────
    anchors.append(_make(
        "reverb, small room, tight ambience, studio room sound, close",
        **{"reverb.active": True, "reverb.size": 0.2, "reverb.damping": 0.6, "reverb.mix": 0.25},
    ))
    anchors.append(_make(
        "reverb, medium hall, warm space, natural, live room",
        **{"reverb.active": True, "reverb.size": 0.5, "reverb.damping": 0.5, "reverb.mix": 0.35},
    ))
    anchors.append(_make(
        "reverb, large hall, spacious, cathedral, epic, vast",
        **{"reverb.active": True, "reverb.size": 0.8, "reverb.damping": 0.4, "reverb.mix": 0.5},
    ))

    # Mode-specific
    all_reverb_modes = set()
    for semantics in _PLUGIN_SEMANTICS.values():
        for mode, mtags in semantics.get("reverb_modes", {}).items():
            if mode not in all_reverb_modes and mode != "Reverb":  # skip generic
                all_reverb_modes.add(mode)
                anchors.append(_make(
                    f"{', '.join(mtags)}, ambient pad, post-rock, atmospheric",
                    **{"reverb.active": True, "reverb.size": 0.85, "reverb.damping": 0.3, "reverb.mix": 0.55},
                ))

    # ── 7. EQ shape anchors ──────────────────────────────────────────
    anchors.append(_make(
        "bright, treble boost, sparkly, airy, presence, cutting",
        **{"amp.treble": 0.8, "amp.presence": 0.7, "amp.bass": 0.4},
    ))
    anchors.append(_make(
        "dark, warm, rolled off highs, mellow, smooth, thick",
        **{"amp.treble": 0.3, "amp.presence": 0.3, "amp.bass": 0.65},
    ))
    anchors.append(_make(
        "mid-scoop, scooped mids, thrash metal EQ, V-curve",
        **{"amp.bass": 0.7, "amp.mid": 0.25, "amp.treble": 0.7},
    ))
    anchors.append(_make(
        "mid-forward, mid-hump, blues tone, vocal mids, honky",
        **{"amp.bass": 0.45, "amp.mid": 0.75, "amp.treble": 0.45},
    ))

    # ── 8. Common combination anchors ────────────────────────────────
    anchors.append(_make(
        "overdrive, delay, rock lead with echo, soaring solo, sustain with repeats",
        **{"overdrive.active": True, "overdrive.drive": 0.5, "overdrive.tone": 0.55,
           "overdrive.level": 0.65, "delay.active": True, "delay.time": 0.4,
           "delay.feedback": 0.3, "delay.mix": 0.3, "amp.character": "crunch", "amp.gain": 0.55},
    ))
    anchors.append(_make(
        "compression, reverb, clean ambient, pad, sustained clean, atmospheric",
        **{"compressor.active": True, "compressor.compression": 0.5,
           "reverb.active": True, "reverb.size": 0.7, "reverb.mix": 0.45,
           "amp.gain": 0.25},
    ))
    anchors.append(_make(
        "overdrive, reverb, shoegaze, wall of sound, dreamy distortion",
        **{"overdrive.active": True, "overdrive.drive": 0.6, "overdrive.tone": 0.4,
           "overdrive.level": 0.6, "reverb.active": True, "reverb.size": 0.85,
           "reverb.mix": 0.55, "amp.character": "crunch", "amp.gain": 0.5},
    ))

    # ── 9. Genre-oriented anchors ────────────────────────────────────
    anchors.append(_make(
        "blues, warm crunch, Texas blues, SRV, Stevie Ray, slightly dirty",
        **{"amp.character": "crunch", "amp.gain": 0.45, "amp.mid": 0.6,
           "amp.treble": 0.55, "overdrive.active": True, "overdrive.drive": 0.3,
           "overdrive.tone": 0.45, "overdrive.level": 0.55},
    ))
    anchors.append(_make(
        "jazz, warm clean, round tone, mellow, smooth, no distortion",
        **{"amp.character": "clean", "amp.gain": 0.2, "amp.bass": 0.55,
           "amp.mid": 0.5, "amp.treble": 0.35, "amp.presence": 0.3},
    ))
    anchors.append(_make(
        "metal, heavy distortion, chug, palm mute, aggressive, djent, tight",
        **{"amp.character": "lead", "amp.gain": 0.85, "amp.bass": 0.45,
           "amp.mid": 0.5, "amp.treble": 0.6, "amp.presence": 0.65},
    ))
    anchors.append(_make(
        "ambient, post-rock, atmospheric, spacious, clean delay reverb wash",
        **{"amp.character": "clean", "amp.gain": 0.2,
           "delay.active": True, "delay.time": 0.6, "delay.feedback": 0.45,
           "delay.mix": 0.4, "reverb.active": True, "reverb.size": 0.8,
           "reverb.mix": 0.5},
    ))
    anchors.append(_make(
        "country, twang, chicken picking, clean bright, Telecaster snap",
        **{"amp.character": "clean", "amp.gain": 0.3, "amp.treble": 0.7,
           "amp.presence": 0.65, "compressor.active": True,
           "compressor.compression": 0.4},
    ))
    anchors.append(_make(
        "funk, tight clean, percussive, snappy, wah-like, envelope filter",
        **{"amp.character": "clean", "amp.gain": 0.3, "amp.mid": 0.55,
           "amp.treble": 0.6, "compressor.active": True,
           "compressor.compression": 0.5},
    ))

    return anchors


def add_coverage_anchors(anchors: list[dict]) -> list[dict]:
    """Remove previous coverage anchors and add fresh ones.

    Args:
        anchors: Existing anchor list (factory + any other synthetic).
    Returns:
        Updated anchor list with coverage anchors appended.
    """
    # Remove previous coverage anchors (and legacy [Pure] anchors)
    filtered = [a for a in anchors
                if not a.get("preset_name", "").startswith("[Coverage]")
                and not a.get("preset_name", "").startswith("[Pure]")]

    coverage = generate_coverage_anchors()
    filtered.extend(coverage)

    return filtered


def main():
    with open(ANCHOR_PATH) as f:
        anchors = yaml.safe_load(f)

    anchors = add_coverage_anchors(anchors)

    with open(ANCHOR_PATH, "w") as f:
        yaml.dump(anchors, f, default_flow_style=False, sort_keys=False, width=120)

    n_coverage = sum(1 for a in anchors if a.get("preset_name", "").startswith("[Coverage]"))
    n_factory = len(anchors) - n_coverage
    print(f"Anchors: {n_factory} factory + {n_coverage} coverage = {len(anchors)} total")

    # Show coverage anchors
    print(f"\nCoverage anchors ({n_coverage}):")
    for a in anchors:
        if a.get("preset_name", "").startswith("[Coverage]"):
            print(f"  {a['description'][:80]}")


if __name__ == "__main__":
    main()
