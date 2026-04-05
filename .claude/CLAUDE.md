# NeuralDSP NLP Controller — Codebase Context

## What This Is

An NLP-controlled real-time tone engine for Neural DSP Archetype guitar plugins. Users type a tone description and the system matches it to factory presets, loads them into the plugin, and plays live audio through their guitar.

## Architecture

```text
User text → NLP Engine → Top-K preset matches → Raw Preset Loader → VST3 Plugin → Audio Out
              ↑                                       ↑
       Anchor DB (~422 presets)                Preset files (.xml)
       honest canonical descriptions           ~170 raw params
```

### Two-Layer Design

1. **Canonical layer** (15 params, 0-1 normalized) — used for NLP descriptions and refinement delta math. NOT used for audio rendering.
2. **Raw layer** (all ~170 params) — used for actual audio: preset loading, blending. Lossless.

### Honest descriptions only

All anchor descriptions are derived from values the adapter measured from the loaded plugin state (canonical tone) plus the preset's own name. No hand-written stylistic claims ("Vox-style", "Fender-style") and no synthetic coverage anchors — V1 Clean stays close to what we can measure.

### NLP ↔ DSP Separation

The NLP engine knows nothing about specific plugins. The adapter/preset_loader knows nothing about NLP. They communicate through the canonical schema. This means:

- Swapping DSP backend (Neural DSP → NAM → custom) only requires a new adapter
- Improving NLP doesn't touch the audio path

## Module Map

```text
src/neuraldsp_nlp_controller/
├── nlp_engine.py      # Text → top-K anchor matches via sentence-transformer embeddings
├── canonical.py       # CanonicalTone dataclass (15 params, 0-1 normalized)
├── anchor_builder.py  # Builds anchor DB: load preset → extract canonical → describe → save
├── adapter.py         # Canonical ↔ plugin params (extract/apply/apply_delta)
├── preset_loader.py   # Raw preset parsing, loading, blending, auto-discovered mapping
└── refinement.py      # Delta commands ("less fizzy", "brighter") → canonical param adjustments
```

### Data Flow for Each User Action

**New query ("warm blues crunch"):**

1. `nlp_engine.query()` embeds text, cosine similarity vs ~422 preset anchor embeddings
2. Returns top-5 matches with scores, preset paths, descriptions
3. User selects one → `preset_loader.load_preset()` loads all ~170 raw params into plugin
4. Or user clicks "Blend All" → `preset_loader.blend_presets()` weighted-averages raw params

**Refinement ("less fizzy"):**

1. User types into the separate refinement textbox (enabled only after a tone is loaded)
2. `refinement.parse_deltas()` maps keywords → canonical param deltas (with fuzzy typo tolerance)
3. `adapter.apply_delta()` reads current plugin values, applies delta, sets new values

**Anchor DB rebuild:**

1. `anchor_builder.build_anchors()` iterates all factory presets across all plugins
2. For each: loads preset → `adapter.extract()` gets canonical tone → `_describe_tone()` builds description from canonical values + preset name
3. `save_anchors()` writes to `data/anchors.yaml`

## Key Files

| File | What to read it for |
| --- | --- |
| `app.py` | Gradio UI, audio streaming, main-thread loader queue |
| `data/anchors.yaml` | The anchor database (~422 preset entries) |
| `pyproject.toml` | Dependencies and build config |

## Build & Run

```bash
# Install deps
uv sync

# Build anchor database (~8 min, one-time per preset set)
uv run python scripts/build_anchor_db.py

# Run the app
uv run python app.py
```

## Scripts

| Script | Purpose |
| --- | --- |
| `scripts/build_anchor_db.py` | Build `data/anchors.yaml` from factory presets |
| `scripts/investigate_preset_names.py` | Research: A/B test preset names vs no-names |
| `scripts/explore_param_semantics.py` | Research: analyze param variance across presets |
| `scripts/phase0_validate.py` | Phase 0 validation script (AudioStream test) |
| `scripts/test_preset_loader.py` | Preset loader accuracy test |
| `scripts/auto_discover_mapping.py` | Discover preset-key → pedalboard-param mapping |

## Adding a New Plugin

1. Add VST3 path + preset dir to `anchor_builder.py` → `PLUGINS` list
2. Add amp channel mapping to `adapter.py` → `_AMP_CHANNELS` dict
3. Add effect param mapping to `adapter.py` → `_EFFECTS` dict
4. Run `uv run python scripts/build_anchor_db.py`

See `docs/adding-plugins.md` for detailed guide.

## Threading Model

VST3 plugins require main thread for loading on macOS (Cocoa). Gradio runs callbacks in worker threads. Solution:

- `app.py` uses `prevent_thread_lock=True` so Gradio runs in background
- Main thread runs `_main_thread_loader_loop()` — polls a `queue.Queue` for load requests
- Worker threads post load requests and wait on `threading.Event`

## Design Decisions

- **Honest canonical descriptions** — derived from adapter measurements, not hand-written style claims
- **Preset anchors only** — no synthetic coverage anchors; retrieval surfaces real gaps instead of hiding them
- **Sentence-transformers** (all-MiniLM-L6-v2) for embeddings — fast, good for short descriptions
- **Raw preset loading bypasses canonical for audio** — canonical is NLP/refinement layer only
- **Separate search and refinement inputs** — explicit mode, no keyword-based guessing
- **Refinement via fuzzy keyword match** on canonical param deltas (typo tolerant)

## Supported Plugins (current)

- Archetype Tim Henson X (189 presets)
- Archetype Cory Wong X (233 presets)
