# Neural DSP NLP Controller

Type your tone, hear it instantly. An NLP-powered real-time tone controller for Neural DSP Archetype guitar plugins.

```
You: "warm Vox crunch with slapback delay"
→ Matches factory presets by meaning, not keywords
→ Loads the best match into your plugin
→ Guitar plays through it live
```

## How It Works

1. **You describe a tone** in natural language
2. **The NLP engine** embeds your description and finds the closest matches from 462 anchors (factory presets + synthetic coverage anchors)
3. **The preset loader** loads the full factory preset (~170 parameters) into the Neural DSP plugin — lossless, no information lost
4. **You play guitar** through it in real-time via audio streaming
5. **You refine** with delta commands: "less fizzy", "brighter", "more reverb" — modifies the current tone in-place

## Requirements

- macOS (VST3 plugins require main thread / Cocoa)
- At least one Neural DSP Archetype plugin installed:
  - Archetype Tim Henson X
  - Archetype Cory Wong X
- An audio interface (guitar in, headphones/monitors out)
- Python 3.11+

## Quick Start

```bash
# 1. Clone
git clone https://github.com/gendsp/neuraldsp-nlp-controller.git
cd neuraldsp-nlp-controller

# 2. Install dependencies (uses uv)
uv sync

# 3. Build the anchor database from YOUR Neural DSP presets (~10 min, one-time)
uv run python scripts/build_anchor_db.py

# 4. Run the app
uv run python app.py
```

Open the Gradio URL in your browser, select your audio device and plugin, and start typing tones.

## Setting Up the Anchor Database

The anchor database is the core of NLP matching — it's a list of tone "anchors" (presets + semantic descriptions) that your text query gets matched against. You build it once from your own installed Neural DSP plugins.

### Why you build it locally

This project doesn't ship factory preset data — those are Neural DSP's copyrighted work. Instead, on first run you build the anchor database **from your own legally-owned preset files** on your machine. The repo only ships `data/anchors.example.yaml` containing 40 synthetic coverage anchors (no preset data).

### What the build script does

`scripts/build_anchor_db.py` runs a three-step pipeline:

1. **Discover plugins** — looks for installed Neural DSP Archetype VST3s at `/Library/Audio/Plug-Ins/VST3/` and their factory preset dirs at `/Library/Audio/Presets/Neural DSP/`
2. **Extract factory anchors** — for each preset file (~422 across Tim Henson X + Cory Wong X):
   - Loads the preset into the plugin
   - Reads all ~170 raw parameters
   - Extracts canonical tone (15 normalized params) via `adapter.py`
   - Extracts rich semantic tags ("Vox-style crunch", "modern delay", "dynamic mic punch") from raw params via `semantic_extractor.py`
   - Combines preset name + tags into a searchable description
3. **Add coverage anchors** — generates 40 synthetic anchors via `generate_coverage_anchors.py` covering amp archetypes, effect types, EQ shapes, and common genres (fills gaps the factory presets don't cover)
4. **Save** to `data/anchors.yaml` (gitignored)

### Running it

```bash
uv run python scripts/build_anchor_db.py
```

Expected output:

```text
Building anchor database from factory presets...
Built 422 factory anchors in 480.3s
Added 40 coverage anchors
Total: 462 anchors in 481.1s

Sample descriptions:
  [Archetype Tim He] Arch Echo Clean Comp, Vox-style crunch, chimey, moderate gain, ...
  ...

Archetype Tim Henson X: 189 anchors
Archetype Cory Wong X: 233 anchors
Character distribution: {'clean': 187, 'crunch': 142, 'high_gain': 89, 'lead': 44}

Saved to data/anchors.yaml
```

Takes **~8–10 minutes** (dominated by VST3 loading, not NLP). Runs once — only re-run when you install a new plugin or update presets.

### Verifying it worked

```bash
# Check the file exists and has content
wc -l data/anchors.yaml            # Should be thousands of lines
grep -c "^- description:" data/anchors.yaml   # Should be ~462
```

Then launch the app (`uv run python app.py`) — on startup it prints `NNN anchors loaded.`

### Troubleshooting

| Problem | Fix |
| --- | --- |
| `No Neural DSP plugins found` | Confirm `.vst3` files exist at `/Library/Audio/Plug-Ins/VST3/Archetype *.vst3` |
| `No factory presets found` | Confirm `.xml` preset files exist at `/Library/Audio/Presets/Neural DSP/Archetype .../` |
| Script crashes on a specific preset | Delete the problem preset file or skip that plugin in `anchor_builder.py` → `PLUGINS` list |
| Descriptions look thin (missing semantic tags) | Check that your plugin is listed in `semantic_extractor.py` → `_PLUGIN_SEMANTICS`; add config if not (see [docs/adding-plugins.md](docs/adding-plugins.md)) |
| Want to rebuild from scratch | Just re-run the script — it overwrites `data/anchors.yaml` |

## Features

### Semantic Tone Matching

Describe tones naturally. The engine understands concepts like "Fender-style clean", "British crunch", "ambient post-rock", "Texas blues", not just keywords.

### Stateful Refinement

Build on your current tone instead of starting over:

- "less fizzy" → reduces treble/presence
- "more gain" → increases amp gain and drive
- "add delay" → activates delay with sensible defaults
- "brighter" → boosts treble and presence

### Lossless Preset Loading

Loads all ~170 raw parameters from factory presets — not a lossy 15-parameter approximation. What the preset designer intended is exactly what you hear.

### Raw Preset Blending

Blend multiple presets by weighted-averaging all numeric parameters. Creates tones that don't exist in any single preset.

### Auto-Generated Descriptions

Each factory preset gets 10-15 semantic tags auto-extracted from its raw parameters: amp character, gain staging, EQ shape, effect types, mic character, and more. No manual labeling needed.

## Architecture

```text
User text ──→ NLP Engine ──→ Top-K matches ──→ Preset Loader ──→ VST3 Plugin ──→ Audio
                  ↑                                   ↑
           Anchor DB (462)                     Factory presets
           semantic embeddings                 ~170 raw params
```

The system has a clean separation between NLP and DSP:

- **NLP side** (embeddings, matching, refinement) knows nothing about specific plugins
- **DSP side** (preset loading, parameter mapping) knows nothing about NLP
- They communicate through a canonical tone schema (15 normalized params)

This means the NLP engine can be reused with any DSP backend — Neural DSP today, NAM or custom DSP tomorrow.

See [docs/architecture.md](docs/architecture.md) for full details.

## Adding a New Plugin

The system is designed to scale. Adding a new Neural DSP Archetype plugin requires:

1. ~5 lines: plugin path and preset directory
2. ~10 lines: amp channel mapping
3. ~30 lines: semantic config (amp types, delay types, mic types)
4. Run one script to rebuild the anchor database

See [docs/adding-plugins.md](docs/adding-plugins.md) for a step-by-step guide.

## Project Structure

```text
neuraldsp-nlp-controller/
├── app.py                              # Gradio UI + audio streaming
├── src/neuraldsp_nlp_controller/
│   ├── nlp_engine.py                   # Text → tone matching via embeddings
│   ├── canonical.py                    # Canonical tone schema (15 params)
│   ├── semantic_extractor.py           # Raw params → semantic tags
│   ├── anchor_builder.py              # Builds anchor database
│   ├── adapter.py                      # Canonical ↔ plugin params
│   ├── preset_loader.py               # Raw preset parsing + loading
│   └── refinement.py                   # Delta commands ("less fizzy")
├── scripts/
│   ├── build_anchor_db.py             # Rebuild anchor database
│   └── generate_coverage_anchors.py   # Systematic coverage anchors
├── data/
│   └── anchors.yaml                   # 462 anchor entries
└── docs/
    ├── architecture.md                # System design + data flows
    └── adding-plugins.md             # Guide: add a new plugin
```

## How the NLP Works

The NLP engine uses [sentence-transformers](https://www.sbert.net/) (all-MiniLM-L6-v2) to embed text descriptions into a vector space. Each factory preset gets a rich description auto-generated from its raw parameters:

> "Arch Echo Clean Comp, Vox-style crunch, chimey, British, moderate gain, modern delay, clean repeats, rhythmic delay, wide stereo delay, hall reverb, dynamic mic punch"

When you type "British crunch with delay", the engine finds the closest descriptions by cosine similarity, then loads the matching preset.

The refinement system detects commands like "less fizzy" or "brighter" and applies targeted parameter adjustments to the current tone — no full re-search needed.

## License

GPL-3.0. See [LICENSE](LICENSE).

This project depends on [pedalboard](https://github.com/spotify/pedalboard) (GPL-3.0) for VST3 hosting, so GPL-3.0 is required for distribution compatibility.

## Disclaimer

This project is **not affiliated with, endorsed by, or sponsored by Neural DSP Technologies**. Neural DSP® and Archetype® are trademarks of Neural DSP Technologies Oy. This is an independent interoperability tool for users who have legally purchased Neural DSP plugins.

The project does not bundle or redistribute Neural DSP software or factory presets. Users must install the Neural DSP plugins themselves. The anchor database is generated locally from the user's own legally-owned preset files.

## Acknowledgments

Built with:

- [pedalboard](https://github.com/spotify/pedalboard) — VST3 plugin hosting and audio streaming
- [sentence-transformers](https://www.sbert.net/) — text embeddings
- [Gradio](https://gradio.app/) — UI
- [Neural DSP](https://neuraldsp.com/) — the incredible Archetype plugins
