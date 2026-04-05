"""Add synthetic 'pure effect' anchors to the anchor database.

These anchors isolate individual effects with a neutral amp, giving the
NLP engine semantic grounding for effect-specific queries like "overdrive",
"reverb", "chorus" etc.

Usage:
  uv run python scripts/add_pure_effect_anchors.py
"""

import yaml
from pathlib import Path

ANCHOR_PATH = Path(__file__).parent.parent / "data" / "anchors.yaml"

# Neutral amp baseline — clean, flat EQ, moderate gain
_NEUTRAL_AMP = {
    "character": "clean",
    "gain": 0.4,
    "bass": 0.5,
    "mid": 0.5,
    "treble": 0.5,
    "presence": 0.5,
    "master": 0.5,
    "output": 0.5,
}

_OFF_OD = {"active": False, "drive": 0.5, "tone": 0.5, "level": 0.5}
_OFF_COMP = {"active": False, "attack": 0.5, "release": 0.5, "compression": 0.5}
_OFF_CHORUS = {"active": False, "rate": 0.5, "depth": 0.5, "mix": 0.5}
_OFF_DELAY = {"active": False, "time": 0.5, "feedback": 0.5, "mix": 0.5}
_OFF_REVERB = {"active": False, "size": 0.5, "damping": 0.5, "mix": 0.5}


def _make_anchor(description: str, **overrides) -> dict:
    """Create a pure effect anchor with neutral base + specified overrides."""
    tone = {
        "overdrive": {**_OFF_OD},
        "compressor": {**_OFF_COMP},
        "amp": {**_NEUTRAL_AMP},
        "chorus": {**_OFF_CHORUS},
        "delay": {**_OFF_DELAY},
        "reverb": {**_OFF_REVERB},
    }
    for key, val in overrides.items():
        section, param = key.split(".", 1)
        tone[section][param] = val

    return {
        "description": description,
        "tone": tone,
        "plugin_name": "",  # not plugin-specific
        "preset_name": f"[Pure] {description.split(',')[0]}",
        "preset_path": "",  # synthetic, no file
    }


PURE_ANCHORS = [
    # Overdrive variations
    _make_anchor(
        "overdrive, light drive boost, edge of breakup, warm push",
        **{"overdrive.active": True, "overdrive.drive": 0.3, "overdrive.tone": 0.5, "overdrive.level": 0.6},
    ),
    _make_anchor(
        "overdrive, heavy drive, crunchy saturation, tube screamer",
        **{"overdrive.active": True, "overdrive.drive": 0.7, "overdrive.tone": 0.6, "overdrive.level": 0.7},
    ),

    # Compressor variations
    _make_anchor(
        "compressor, light compression, subtle squeeze, even dynamics",
        **{"compressor.active": True, "compressor.compression": 0.3, "compressor.attack": 0.4},
    ),
    _make_anchor(
        "compressor, heavy compression, squashed, sustained, studio squeeze",
        **{"compressor.active": True, "compressor.compression": 0.8, "compressor.attack": 0.6},
    ),

    # Chorus variations
    _make_anchor(
        "chorus, subtle shimmer, light modulation, clean width",
        **{"chorus.active": True, "chorus.rate": 0.3, "chorus.depth": 0.3, "chorus.mix": 0.3},
    ),
    _make_anchor(
        "chorus, lush 80s chorus, thick modulation, wide stereo, detuned",
        **{"chorus.active": True, "chorus.rate": 0.4, "chorus.depth": 0.7, "chorus.mix": 0.6},
    ),

    # Delay variations
    _make_anchor(
        "delay, slapback echo, rockabilly, short repeat",
        **{"delay.active": True, "delay.time": 0.15, "delay.feedback": 0.15, "delay.mix": 0.4},
    ),
    _make_anchor(
        "delay, long ambient echo, spacious, atmospheric, trailing repeats",
        **{"delay.active": True, "delay.time": 0.6, "delay.feedback": 0.5, "delay.mix": 0.4},
    ),
    _make_anchor(
        "delay, dotted eighth, rhythmic delay, the edge, U2 style",
        **{"delay.active": True, "delay.time": 0.45, "delay.feedback": 0.35, "delay.mix": 0.35},
    ),

    # Reverb variations
    _make_anchor(
        "reverb, small room, tight ambience, studio room sound",
        **{"reverb.active": True, "reverb.size": 0.2, "reverb.damping": 0.6, "reverb.mix": 0.25},
    ),
    _make_anchor(
        "reverb, large hall, spacious, cathedral, epic",
        **{"reverb.active": True, "reverb.size": 0.8, "reverb.damping": 0.4, "reverb.mix": 0.5},
    ),
    _make_anchor(
        "reverb, shimmer reverb, ethereal, ambient pad, post-rock",
        **{"reverb.active": True, "reverb.size": 0.9, "reverb.damping": 0.3, "reverb.mix": 0.6},
    ),

    # Amp character anchors (no effects, just amp tones)
    _make_anchor(
        "clean, crystal clear, no effects, pure clean tone, jazz clean",
        **{"amp.character": "clean", "amp.gain": 0.2, "amp.treble": 0.6},
    ),
    _make_anchor(
        "crunch, classic rock crunch, edge of breakup, rhythm crunch",
        **{"amp.character": "crunch", "amp.gain": 0.5},
    ),
    _make_anchor(
        "high gain, heavy distortion, metal rhythm, chug, palm mute",
        **{"amp.character": "lead", "amp.gain": 0.85, "amp.bass": 0.4, "amp.mid": 0.55, "amp.treble": 0.6},
    ),
    _make_anchor(
        "lead, smooth sustain, singing lead tone, solo, legato",
        **{"amp.character": "lead", "amp.gain": 0.7, "amp.mid": 0.65, "amp.treble": 0.55},
    ),
]


def main():
    # Load existing anchors
    with open(ANCHOR_PATH) as f:
        anchors = yaml.safe_load(f)

    # Remove any previous pure anchors (re-runnable)
    anchors = [a for a in anchors if not a.get("preset_name", "").startswith("[Pure]")]

    # Append pure anchors
    anchors.extend(PURE_ANCHORS)

    # Save
    with open(ANCHOR_PATH, "w") as f:
        yaml.dump(anchors, f, default_flow_style=False, sort_keys=False, width=120)

    n_factory = len(anchors) - len(PURE_ANCHORS)
    print(f"Anchors: {n_factory} factory + {len(PURE_ANCHORS)} pure = {len(anchors)} total")


if __name__ == "__main__":
    main()
