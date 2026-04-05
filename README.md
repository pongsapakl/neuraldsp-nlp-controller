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

### Why the anchor build step?

This project doesn't ship factory preset data — those are Neural DSP's copyrighted work. Instead, on first run you build the anchor database **from your own legally-owned preset files** on your machine. The script reads each preset, extracts tonal characteristics, and generates the semantic descriptions used for NLP matching.

The repo ships `data/anchors.example.yaml` containing only the 40 synthetic coverage anchors (amp archetypes, effect types, genres) — no preset data. After running `build_anchor_db.py`, your `data/anchors.yaml` will have these plus anchors for every preset you own.

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

```
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

```
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
