# NeuralDSP NLP Controller — Codebase Context

## What This Is

An NLP-controlled real-time tone engine for Neural DSP Archetype guitar plugins. Users type a tone description ("warm Vox crunch with slapback delay") and the system matches it to factory presets, loads them into the plugin, and plays live audio through their guitar.

## Architecture

```
User text → NLP Engine → Top-K matches → Raw Preset Loader → VST3 Plugin → Audio Out
              ↑                                ↑
        Anchor DB (462 entries)         Preset files (.xml)
        with semantic descriptions      with ~170 raw params
```

### Two-Layer Design

1. **Canonical layer** (15 params, 0-1 normalized) — used ONLY for NLP matching/descriptions and future V2 migration. NOT used for audio.
2. **Raw layer** (all ~170 params) — used for actual audio: preset loading, blending, delta application. Lossless.

### Key Principle: NLP ↔ DSP Separation

The NLP engine knows nothing about specific plugins. The adapter/preset_loader knows nothing about NLP. They communicate through the canonical schema. This means:
- Swapping DSP backend (Neural DSP → NAM → custom) only requires a new adapter
- Improving NLP (better embeddings, LLM, etc.) doesn't touch the audio path

## Module Map

```
src/neuraldsp_nlp_controller/
├── nlp_engine.py          # Text → top-K anchor matches via sentence-transformer embeddings
├── canonical.py           # CanonicalTone dataclass (15 params, 0-1 normalized)
├── anchor_builder.py      # Builds anchor DB: load preset → extract canonical → describe → save
├── semantic_extractor.py  # Extracts rich tonal tags from all ~170 raw params (rule-based)
├── adapter.py             # Canonical ↔ plugin params (extract/apply/apply_delta)
├── preset_loader.py       # Raw preset parsing, loading, blending, auto-discovered mapping
└── refinement.py          # Delta commands ("less fizzy", "brighter") → param adjustments
```

### Data Flow for Each User Action

**New query ("warm blues crunch"):**
1. `nlp_engine.query()` embeds text, cosine similarity vs 462 anchor embeddings
2. Returns top-5 matches with scores, preset paths, descriptions
3. User selects one → `preset_loader.load_preset()` loads all ~170 raw params into plugin
4. Or user clicks "Blend" → `preset_loader.blend_presets()` weighted-averages raw params

**Refinement ("less fizzy"):**
1. `refinement.is_refinement()` detects delta command
2. `refinement.parse_deltas()` maps keywords → canonical param deltas
3. `adapter.apply_delta()` reads current plugin values, applies delta, sets new values

**Anchor DB rebuild:**
1. `anchor_builder.build_anchors()` iterates all factory presets across all plugins
2. For each: loads preset → `adapter.extract()` gets canonical → `semantic_extractor.extract_semantic_tags()` gets rich tags
3. `_describe_tone()` combines preset name + semantic tags into description string
4. `generate_coverage_anchors.add_coverage_anchors()` adds 40 synthetic anchors for gaps

## Key Files

| File | What to read it for |
|------|-------------------|
| `app.py` | Gradio UI, audio streaming, main-thread loader queue |
| `data/anchors.yaml` | The full anchor database (462 entries) |
| `pyproject.toml` | Dependencies and build config |

## Build & Run

```bash
# Install deps
uv sync

# Run the app (requires Neural DSP plugin + audio interface)
uv run python app.py

# Rebuild anchor database (takes ~10 min, loads every preset)
uv run python scripts/build_anchor_db.py
```

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/build_anchor_db.py` | Full pipeline: factory anchors + coverage anchors → anchors.yaml |
| `scripts/generate_coverage_anchors.py` | Systematic coverage anchors (40 entries) |
| `scripts/add_pure_effect_anchors.py` | Legacy — superseded by generate_coverage_anchors.py |
| `scripts/explore_param_semantics.py` | Research: analyze param variance across presets |
| `scripts/investigate_preset_names.py` | Research: A/B test preset names vs no-names |
| `scripts/phase0_validate.py` | Phase 0 validation script (AudioStream test) |
| `scripts/test_preset_loader.py` | Preset loader accuracy test |

## Adding a New Plugin

1. Add VST3 path + preset dir to `anchor_builder.py` → `PLUGINS` list
2. Add amp channel mapping to `adapter.py` → `_AMP_CHANNELS` dict
3. Add effect param mapping to `adapter.py` → `_EFFECTS` dict
4. Add semantic config to `semantic_extractor.py` → `_PLUGIN_SEMANTICS` dict (~30 lines)
5. Run `uv run python scripts/build_anchor_db.py`

See `docs/adding-plugins.md` for detailed guide.

## Threading Model

VST3 plugins require main thread for loading on macOS (Cocoa). Gradio runs callbacks in worker threads. Solution:
- `app.py` uses `prevent_thread_lock=True` so Gradio runs in background
- Main thread runs `_main_thread_loader_loop()` — polls a `queue.Queue` for load requests
- Worker threads post load requests and wait on `threading.Event`

## Design Decisions

- **Rule-based semantic extraction** (not ML) — raw params are structured, ~30 lines config per plugin
- **Sentence-transformers** (all-MiniLM-L6-v2) for embeddings — fast, good for short descriptions
- **Exponential-decay blending** for top-K interpolation — same algorithm as 1P plugin
- **Raw preset loading** bypasses canonical for audio — canonical is semantic-only layer

## Supported Plugins (current)

- Archetype Tim Henson X (189 presets)
- Archetype Cory Wong X (233 presets)
