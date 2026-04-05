"""Build anchor database from Neural DSP factory presets.

Each anchor = {description, canonical_tone, embedding, metadata}.
Descriptions are auto-generated from preset name + tone characteristics.

Usage:
  from neuraldsp_nlp_controller.anchor_builder import build_anchors
  anchors = build_anchors()  # builds from all installed plugins
"""

import yaml
from dataclasses import asdict
from pathlib import Path

from pedalboard import load_plugin

from .adapter import extract
from .canonical import CanonicalTone
from .preset_loader import discover_mapping, list_factory_presets, load_preset
from .semantic_extractor import extract_semantic_tags


PLUGINS = [
    ("/Library/Audio/Plug-Ins/VST3/Archetype Tim Henson X.vst3",
     "/Library/Audio/Presets/Neural DSP/Archetype Tim Henson X"),
    ("/Library/Audio/Plug-Ins/VST3/Archetype Cory Wong X.vst3",
     "/Library/Audio/Presets/Neural DSP/Archetype Cory Wong X"),
]


def _describe_tone(tone: CanonicalTone, preset_name: str,
                   semantic_tags: list[str] | None = None) -> str:
    """Auto-generate a text description from preset name + semantic tags.

    Uses rich semantic tags extracted from raw params (all ~170) when
    available, falling back to canonical-only description otherwise.
    Deduplicates overlapping terms between preset name, semantic tags,
    and canonical descriptors.
    """
    parts = [preset_name]

    if semantic_tags:
        # Semantic tags already cover amp character, gain, EQ, effects
        # in much richer detail than canonical — use them directly
        parts.extend(semantic_tags)
    else:
        # Fallback: canonical-only description (for pure/synthetic anchors)
        char_desc = {
            "clean": "clean",
            "crunch": "crunch, edge of breakup",
            "high_gain": "high gain, heavy distortion",
            "lead": "lead, sustained, mid-focused",
        }
        parts.append(char_desc.get(tone.amp.character, tone.amp.character))

        g = tone.amp.gain
        if g < 0.2:
            parts.append("very low gain, clean headroom")
        elif g < 0.4:
            parts.append("low gain, gentle warmth")
        elif g < 0.6:
            parts.append("moderate gain")
        elif g < 0.8:
            parts.append("high gain, saturated")
        else:
            parts.append("very high gain, fully saturated")

        bass, mid, treble = tone.amp.bass, tone.amp.mid, tone.amp.treble
        if treble > 0.65 and bass < 0.4:
            parts.append("bright, scooped lows")
        elif bass > 0.65 and treble < 0.4:
            parts.append("dark, heavy low end")
        elif mid > 0.65:
            parts.append("mid-forward")
        elif mid < 0.35:
            parts.append("scooped mids")
        if treble > 0.7:
            parts.append("sparkly top end")
        if bass > 0.7:
            parts.append("thick low end")

        if tone.overdrive.active:
            if tone.overdrive.drive > 0.6:
                parts.append("overdrive, driven hard")
            else:
                parts.append("light overdrive boost")

        if tone.compressor.active:
            if tone.compressor.compression > 0.6:
                parts.append("heavy compression, squashed")
            else:
                parts.append("light compression")

        if tone.chorus.active:
            if tone.chorus.mix > 0.5:
                parts.append("lush chorus, wide stereo")
            else:
                parts.append("subtle chorus")

        if tone.delay.active:
            if tone.delay.mix > 0.4:
                parts.append("prominent delay, ambient")
            elif tone.delay.mix > 0.15:
                parts.append("delay, echo")
            else:
                parts.append("subtle delay")

        if tone.reverb.active:
            if tone.reverb.mix > 0.5:
                parts.append("lush reverb, spacious")
            elif tone.reverb.mix > 0.2:
                parts.append("reverb, room ambience")
            else:
                parts.append("subtle reverb")

    return ", ".join(parts)


def build_anchors(plugins: list[tuple[str, str]] | None = None) -> list[dict]:
    """Build anchor database from factory presets.

    Returns list of dicts: {description, tone (CanonicalTone dict),
    plugin_name, preset_name, preset_path}
    """
    if plugins is None:
        plugins = PLUGINS

    anchors = []
    for vst3_path, preset_dir in plugins:
        if not Path(vst3_path).exists():
            continue

        plugin = load_plugin(vst3_path)
        plugin_name = Path(vst3_path).stem
        presets = list_factory_presets(preset_dir)
        if not presets:
            continue

        # Discover mapping once per plugin
        key_map = discover_mapping(plugin, presets[0])

        for preset_path in presets:
            # Reload plugin to reset state
            plugin = load_plugin(vst3_path)
            load_preset(plugin, preset_path, key_map)

            tone = extract(plugin)
            tone.preset_name = preset_path.stem
            tone.plugin_name = plugin_name

            # Extract rich semantic tags from full raw params
            semantic_tags = extract_semantic_tags(plugin, preset_path, key_map)
            description = _describe_tone(tone, preset_path.stem, semantic_tags)

            anchors.append({
                "description": description,
                "tone": tone.to_dict(),
                "plugin_name": plugin_name,
                "preset_name": preset_path.stem,
                "preset_path": str(preset_path),
            })

    return anchors


def save_anchors(anchors: list[dict], path: str | Path):
    """Save anchor database to YAML file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(anchors, f, default_flow_style=False, sort_keys=False, width=120)


def load_anchors(path: str | Path) -> list[dict]:
    """Load anchor database from YAML file."""
    with open(path) as f:
        return yaml.safe_load(f)
