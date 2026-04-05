# Adding a New Neural DSP Plugin

This guide walks through adding support for a new Neural DSP Archetype plugin. The system is designed so that adding a plugin requires only configuration — no logic changes.

## Prerequisites

- The Neural DSP plugin must be installed as a VST3 at `/Library/Audio/Plug-Ins/VST3/`
- Factory presets must be at `/Library/Audio/Presets/Neural DSP/`

## Step 1: Register the Plugin

In `src/neuraldsp_nlp_controller/anchor_builder.py`, add the VST3 path and preset directory to the `PLUGINS` list:

```python
PLUGINS = [
    ("/Library/Audio/Plug-Ins/VST3/Archetype Tim Henson X.vst3",
     "/Library/Audio/Presets/Neural DSP/Archetype Tim Henson X"),
    # Add your plugin:
    ("/Library/Audio/Plug-Ins/VST3/Archetype Nolly X.vst3",
     "/Library/Audio/Presets/Neural DSP/Archetype Nolly X"),
]
```

## Step 2: Map Amp Channels

In `src/neuraldsp_nlp_controller/adapter.py`, add to `_AMP_CHANNELS`:

```python
_AMP_CHANNELS = {
    # ... existing plugins ...
    "Archetype Nolly X": {
        "Rhythm":  ("crunch", "rhythm_amp"),    # (canonical_character, pedalboard_prefix)
        "Lead":    ("lead",   "lead_amp"),
        "Clean":   ("clean",  "clean_amp"),
    },
}
```

To find the amp type values and param prefixes:

```python
from pedalboard import load_plugin
p = load_plugin("/Library/Audio/Plug-Ins/VST3/Archetype Nolly X.vst3")

# Find amp type values
print(list(p.parameters["amp_type"].valid_values))

# Find param prefixes (look for *_gain, *_bass, *_treble patterns)
for name in sorted(p.parameters.keys()):
    if "gain" in name or "bass" in name:
        print(name)
```

## Step 3: Map Effect Parameters

In `src/neuraldsp_nlp_controller/adapter.py`, add to `_EFFECTS`:

```python
_EFFECTS = {
    # ... existing plugins ...
    "Archetype Nolly X": {
        "overdrive": {
            "active": "overdrive_active",
            "drive":  "overdrive_drive",
            "tone":   "overdrive_tone",
            "level":  "overdrive_level",
        },
        "compressor": {
            "active":      "compressor_active",
            "compression": "compressor_compression",
        },
        "chorus": {
            "active": "chorus_active",
            "mix":    "chorus_mix",
        },
        "delay": {
            "active":   "delay_active",
            "time":     "delay_time",
            "feedback": "delay_feedback",
            "mix":      "delay_mix",
        },
        "reverb": {
            "active":  "reverb_active",
            "size":    "reverb_decay",
            "damping": "reverb_high_cut",
            "mix":     "reverb_mix",
        },
    },
}
```

To find effect param names:

```python
for name in sorted(p.parameters.keys()):
    for prefix in ["overdrive", "compressor", "chorus", "delay", "reverb"]:
        if name.startswith(prefix):
            print(name)
```

## Step 4: Add Plugin to App (optional)

In `app.py`, add the VST3 path to `PRESET_DIRS` so the app can find the preset directory:

```python
PRESET_DIRS = {
    "Archetype Tim Henson X": "/Library/Audio/Presets/Neural DSP/Archetype Tim Henson X",
    "Archetype Cory Wong X": "/Library/Audio/Presets/Neural DSP/Archetype Cory Wong X",
    "Archetype Nolly X": "/Library/Audio/Presets/Neural DSP/Archetype Nolly X",
}
```

## Step 5: Rebuild Anchor Database

```bash
uv run python scripts/build_anchor_db.py
```

This takes ~10 minutes (loads every preset file). The output will show the new plugin's anchors.

## Step 6: Verify

```bash
# Quick test: check the new anchors exist
uv run python -c "
import yaml
anchors = yaml.safe_load(open('data/anchors.yaml'))
for plugin in set(a['plugin_name'] for a in anchors if a['plugin_name']):
    count = sum(1 for a in anchors if a['plugin_name'] == plugin)
    print(f'{plugin}: {count} anchors')
"
```

## What You Don't Need to Do

- **No changes to `preset_loader.py`** — auto-discovery handles param mapping automatically
- **No changes to `nlp_engine.py`** — it reads from `anchors.yaml`, which now includes the new plugin
- **No changes to `refinement.py`** — refinement works via canonical params, which the adapter translates

## Troubleshooting

**"0 presets found"** — Check that the preset directory exists and contains `.xml` files. Neural DSP presets are in subdirectories (e.g., `Artists/`, `Factory/`).

**Low mapping coverage** — Run `scripts/test_preset_loader.py` to see unmapped params. Most Neural DSP plugins map 155-160 of ~170 params automatically.
