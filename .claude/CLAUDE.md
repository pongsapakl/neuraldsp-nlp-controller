# NeuralDSP NLP Controller — Codebase Context

## What This Is

An NLP-controlled real-time tone engine for Neural DSP Archetype guitar plugins. Users type a tone description and the system matches it to factory presets, loads them into the plugin, and plays live audio through their guitar.

## Core Principles (non-negotiable)

These principles govern every design and implementation decision. They were established through deliberate debate and are documented in `docs/decisions/2026-04-05-v1-clean-no-coverage-no-llm.md`. Do not deviate without explicit user approval.

1. **No LLM in the engine.** No GPT calls, no reasoning models, no generative AI for parameter values. The tone engine is mathematical: embeddings, cosine similarity, rule-based refinement. An LLM-controlled guitar is an AI music agent — that's a different product.

2. **Local-first.** No network calls for tone matching. Everything runs on the user's laptop alongside their DAW. Cloud is only acceptable for optional features (e.g. song upload processing) that don't block the core workflow.

3. **Low-resource.** Must coexist with a DAW + VST3 plugin + real-time audio on a single laptop. Sentence-transformers (~80MB, CPU, milliseconds) is the budget. No 7B+ models, no GPU requirements for core features.

4. **Deterministic.** Same query returns the same preset every time. No sampling, no temperature, no stochastic behavior in the matching pipeline. A guitarist needs to trust that "warm crunch" always gives them the same starting point.

5. **Honest measurements only.** Every description, tag, or label must trace to a value the adapter actually measured from the loaded plugin. If we can't measure it, we don't claim it. No hand-written style labels ("Vox-style", "Fender-style").

6. **Reusable across backends.** The NLP engine and canonical schema must work with any DSP backend (Neural DSP today, NAM tomorrow, custom DSP later). No coupling to specific plugin internals in the matching layer.

7. **Fast, Vast, Easy.** Every feature is graded against these three:
   - **Fast** — type a few words, get a playable tone in seconds
   - **Vast** — cover the full range of tones the plugin can produce
   - **Easy** — sound good out of the box, no knob-twiddling required

8. **This is not an AI music agent.** The product exists so the human plays guitar faster. If a feature moves toward "AI makes music for you", it belongs in a different project.

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
