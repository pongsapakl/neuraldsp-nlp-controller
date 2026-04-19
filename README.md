# Neural DSP NLP Controller

Type your tone, hear it instantly. An NLP-powered real-time tone controller for Neural DSP Archetype guitar plugins.

```
You: "warm crunch with delay"
→ Matches factory presets by meaning, not keywords
→ Loads the best match into your plugin
→ Guitar plays through it live
```

## Why I Built This (Pain Points)

This is a tool I built for myself, not a product pitched at anyone. The pain it scratches:

**Neural DSP makes great-sounding amps, but getting to a good tone takes time.** Factory preset libraries have hundreds of entries with artisanal names ("The Amp Snob", "Ales Lagers and Barleywines") that tell you nothing about what they sound like. You either browse one-by-one, or you commit to tweaking knobs — both pull you out of playing.

Presets are supposed to be the shortcut: click one, sound good immediately. That only works if you can find the right one in seconds. My goal was to keep the one-click promise but replace the browsing with natural-language search.

### Three things this has to be

1. **Fast** — type a few words, get a playable tone. No browsing, no loading screens beyond the initial plugin load.
2. **Vast** — cover the full range of tones the plugin can produce, not a curated subset. If the preset library has it, the search should find it.
3. **Easy** — sound good out of the box, no knob-twiddling required. If you *want* to tweak afterwards, the plugin UI is right there. But you shouldn't *have* to.

Everything in this project is graded against those three. Coverage anchors were removed because they hurt Fast. LLM approaches were rejected because they hurt Easy (latency, determinism) and Fast. The refinement system exists because sometimes Easy means "nudge what's already playing" instead of "search again". The pain point I'm **not** solving is "make music for me" — I want to play the guitar, I just don't want to spend 20 minutes finding the right tone first.

If those three things resonate, this might be useful to you too.

## How It Works

1. **You describe a tone** in natural language
2. **The NLP engine** embeds your description and finds the closest factory-preset matches (~422 anchors, all derived from your own installed presets)
3. **The preset loader** loads the full factory preset (~170 parameters) into the Neural DSP plugin — lossless, no information lost
4. **You play guitar** through it in real-time via audio streaming
5. **You refine** with delta commands in a separate textbox: "less fizzy", "brighter", "more reverb" — modifies the current tone in-place

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

Open http://127.0.0.1:7860 in your browser, select your audio device and plugin, and start typing tones.

The UI is a precompiled React bundle served by FastAPI. To rebuild after editing `web/src/*.jsx`: `cd web && node build.mjs`.

## Setting Up the Anchor Database

The anchor database is the core of NLP matching — it's a list of tone "anchors" (factory presets + auto-generated descriptions) that your text query gets matched against. You build it once from your own installed Neural DSP plugins.

### Why you build it locally

This project doesn't ship factory preset data — those are Neural DSP's copyrighted work. Instead, on first run you build the anchor database **from your own legally-owned preset files** on your machine.

### What the build script does

`scripts/build_anchor_db.py` runs a simple pipeline:

1. **Discover plugins** — looks for installed Neural DSP Archetype VST3s at `/Library/Audio/Plug-Ins/VST3/` and their factory preset dirs at `/Library/Audio/Presets/Neural DSP/`
2. **Extract preset anchors** — for each preset file (~422 across Tim Henson X + Cory Wong X):
   - Loads the preset into the plugin
   - Reads all ~170 raw parameters
   - Extracts canonical tone (15 normalized params) via `adapter.py`
   - Auto-generates an honest description from the preset name + measured canonical values
3. **Save** to `data/anchors.yaml` (gitignored)

All descriptions are derived from values the adapter actually measured — no hand-written stylistic claims ("Vox-style", "Fender-style") and no synthetic coverage anchors. V1 Clean stays close to what we can measure.

### Running it

```bash
uv run python scripts/build_anchor_db.py
```

Expected output:

```text
Building anchor database from factory presets...
Built 422 preset anchors in 480.3s

Archetype Tim Henson X: 189 anchors
Archetype Cory Wong X: 233 anchors
Character distribution: {'clean': 187, 'crunch': 142, 'high_gain': 89, 'lead': 44}

Saved to data/anchors.yaml
```

Takes **~8–10 minutes** (dominated by VST3 loading, not NLP). Runs once — only re-run when you install a new plugin or update presets.

### Verifying it worked

```bash
wc -l data/anchors.yaml                       # Thousands of lines
grep -c "^- description:" data/anchors.yaml   # ~422
```

Then launch the app (`uv run python app.py`) — on startup it prints `NNN anchors loaded.`

### Troubleshooting

| Problem | Fix |
| --- | --- |
| `No Neural DSP plugins found` | Confirm `.vst3` files exist at `/Library/Audio/Plug-Ins/VST3/Archetype *.vst3` |
| `No factory presets found` | Confirm `.xml` preset files exist at `/Library/Audio/Presets/Neural DSP/Archetype .../` |
| Script crashes on a specific preset | Delete the problem preset file or skip that plugin in `anchor_builder.py` → `PLUGINS` list |
| Want to rebuild from scratch | Just re-run the script — it overwrites `data/anchors.yaml` |

## Features

### Semantic Tone Matching

Describe tones naturally using measurable characteristics: gain, EQ shape, effect presence, character. The engine finds the closest presets by meaning — no keyword matching.

### Stateful Refinement (Separate Textbox)

A dedicated refinement input (enabled after a tone is loaded) applies delta commands to your current tone:

- "less fizzy" → reduces treble/presence
- "more gain" → increases amp gain and drive
- "add delay" → increases delay mix
- "brighter" → boosts treble and presence

Refinement is fuzzy-matched for typo tolerance — "more crhnchy" still resolves to "crunch".

### Lossless Preset Loading

Loads all ~170 raw parameters from factory presets — not a lossy 15-parameter approximation. What the preset designer intended is exactly what you hear.

### Raw Preset Blending

Blend multiple presets by weighted-averaging all numeric parameters. Creates tones that don't exist in any single preset.

## Architecture

```text
User text ──→ NLP Engine ──→ Top-K matches ──→ Preset Loader ──→ VST3 Plugin ──→ Audio
                  ↑                                   ↑
           Anchor DB (~422)                    Factory presets
           honest descriptions                 ~170 raw params
```

The system has a clean separation between NLP and DSP:

- **NLP side** (embeddings, matching, refinement) knows nothing about specific plugins
- **DSP side** (preset loading, parameter mapping) knows nothing about NLP
- They communicate through a canonical tone schema (15 normalized params)

This means the NLP engine can be reused with any DSP backend — Neural DSP today, NAM or custom DSP tomorrow.

See [docs/architecture.md](docs/architecture.md) for full details.

## Adding a New Plugin

1. ~5 lines: plugin path and preset directory in `anchor_builder.py`
2. ~10 lines: amp channel mapping in `adapter.py`
3. Run `scripts/build_anchor_db.py` to rebuild the anchor database

See [docs/adding-plugins.md](docs/adding-plugins.md) for a step-by-step guide.

## Project Structure

```text
neuraldsp-nlp-controller/
├── app.py                              # Entry point: audio streaming + main-thread loader
├── server.py                           # FastAPI JSON API + static UI
├── web/                                # React UI (precompiled)
│   ├── index.html
│   ├── src/                            # JSX source
│   ├── static/                         # bundle.js + vendored React
│   └── build.mjs                       # esbuild: JSX → bundle.js
├── src/neuraldsp_nlp_controller/
│   ├── nlp_engine.py                   # Text → tone matching via embeddings
│   ├── canonical.py                    # Canonical tone schema (15 params)
│   ├── anchor_builder.py               # Builds anchor database
│   ├── adapter.py                      # Canonical ↔ plugin params
│   ├── preset_loader.py                # Raw preset parsing + loading
│   └── refinement.py                   # Delta commands ("less fizzy")
├── scripts/
│   └── build_anchor_db.py              # Rebuild anchor database
├── data/
│   └── anchors.yaml                    # ~422 preset anchor entries (gitignored)
└── docs/
    ├── architecture.md                 # System design + data flows
    └── adding-plugins.md               # Guide: add a new plugin
```

## How the NLP Works

The NLP engine uses [sentence-transformers](https://www.sbert.net/) (all-MiniLM-L6-v2) to embed text descriptions into a vector space. Each factory preset gets a description auto-generated from its name + measured canonical values:

> "Arch Echo Clean Comp, clean, low gain, gentle warmth, mid-forward, subtle reverb"

When you type "warm clean with mids", the engine finds the closest descriptions by cosine similarity, then loads the matching preset.

The refinement system parses commands like "less fizzy" or "brighter" and applies targeted parameter adjustments to the current tone — no full re-search needed.

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
- [FastAPI](https://fastapi.tiangolo.com/) + [React](https://react.dev/) — UI + JSON API
- [Neural DSP](https://neuraldsp.com/) — the incredible Archetype plugins
