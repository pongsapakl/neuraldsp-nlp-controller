# Architecture

## System Overview

The system maps natural language tone descriptions to Neural DSP plugin parameters in real-time. It has three distinct layers that communicate through well-defined interfaces.

```
┌─────────────────────────────────────────────────────────────┐
│                        User Interface                        │
│  Gradio app (app.py) — text input, audio device, results    │
└──────────────────┬──────────────────────────────────────────┘
                   │
        ┌──────────▼──────────┐
        │     NLP Layer        │
        │                      │
        │  nlp_engine.py       │  Text → embedding → cosine similarity
        │  refinement.py       │  Delta commands → param adjustments
        │  canonical.py        │  15-param normalized tone schema
        └──────────┬──────────┘
                   │ CanonicalTone (for matching)
                   │ preset_path (for loading)
        ┌──────────▼──────────┐
        │     DSP Layer        │
        │                      │
        │  adapter.py          │  Canonical ↔ plugin-specific params
        │  preset_loader.py    │  Raw preset I/O (~170 params)
        └──────────┬──────────┘
                   │ setattr(plugin, param, value)
        ┌──────────▼──────────┐
        │    Audio Layer       │
        │                      │
        │  pedalboard          │  VST3 hosting + AudioStream
        │  Neural DSP plugin   │  The actual DSP processing
        └─────────────────────┘
```

## Data Flows

### Flow 1: New Tone Query

```
"warm clean with reverb"
        │
        ▼
  NLPEngine.query()
  ├── Embed text (sentence-transformer)
  ├── Cosine similarity vs ~422 preset anchor embeddings
  └── Return top-5: [{description, score, preset_path, tone}, ...]
        │
        ▼
  User selects match #2
        │
        ├── Option A: Exact preset
        │   └── preset_loader.load_preset(plugin, preset_path, key_map)
        │       └── Loads all ~170 raw params into plugin (lossless)
        │
        └── Option B: Blend top-5
            └── preset_loader.blend_presets(plugin, paths, weights, key_map)
                └── Weighted-averages ~150 numeric params, snaps ~20 discrete
```

### Flow 2: Refinement ("less fizzy")

```
"less fizzy"   (typed into the refinement textbox, separate from search)
      │
      ▼
  refinement.parse_deltas()
  ├── "less" → direction = -1
  ├── "fizzy" → maps to {amp.treble: -1, amp.presence: -1}
  └── Returns {amp.treble: -0.1, amp.presence: -0.1}
      │
      ▼
  adapter.apply_delta(plugin, deltas)
  ├── Reads current plugin values
  ├── Normalizes to 0-1 space
  ├── Applies delta, clamps
  └── Sets new values on plugin
```

### Flow 3: Anchor DB Build

```
Factory preset files (.xml)
      │
      ▼
  For each preset:
  ├── preset_loader.load_preset()     →  Load all ~170 params into plugin
  ├── adapter.extract()               →  Read 15 canonical params
  └── anchor_builder._describe_tone() →  Preset name + measured canonical values
      │
      ▼
  data/anchors.yaml (~422 entries)
```

## Module Details

### `nlp_engine.py` — NLP Engine

Embeds text and anchor descriptions using `all-MiniLM-L6-v2` (sentence-transformers). Matching is pure cosine similarity — no LLM, no API calls.

Key methods:
- `query(text, top_k, plugin_name)` → top-K matches with scores and preset paths (used by V1 Clean app)
- `match(text, top_k, sensitivity, plugin_name)` → blended CanonicalTone (kept for library consumers; unused in V1 Clean app, which blends at the raw-preset level via `preset_loader.blend_presets()`)

Blend weighting uses exponential decay: `weight = exp(-(1 - similarity))`.

### `canonical.py` — Canonical Schema

A 15-parameter, 0-1 normalized representation of a guitar tone:

| Section | Fields |
|---------|--------|
| Amp | character (clean/crunch/lead), gain, bass, mid, treble, presence, master, output |
| Overdrive | active, drive, tone, level |
| Compressor | active, attack, release, compression |
| Chorus | active, rate, depth, mix |
| Delay | active, time, feedback, mix |
| Reverb | active, size, damping, mix |

This schema is **not used for audio rendering** — audio always goes through raw preset loading. Canonical is the substrate for two things only: (1) `anchor_builder._describe_tone()` turns canonical values into text for the anchor DB, and (2) `refinement.apply_delta()` operates in canonical space so delta commands can work identically across plugins.

### `adapter.py` — Plugin Adapter

Translates between canonical schema and plugin-specific parameters. Each plugin has different param names (e.g. "roses_amp_gain" vs "the_clean_machine_gain"), different amp channels, and different effect routing.

Key config dicts:
- `_AMP_CHANNELS` — maps amp_type enum → (canonical character, param prefix)
- `_EFFECTS` — maps canonical effect fields → plugin param names

Key functions:
- `extract(plugin)` → reads plugin state into CanonicalTone
- `apply(plugin, tone)` → sets plugin params from CanonicalTone
- `apply_delta(plugin, deltas)` → modifies current plugin params by delta amounts

### `preset_loader.py` — Preset Loader

Handles the raw preset file format (proprietary binary with null-separated key-value pairs) and auto-discovers the mapping between preset keys and pedalboard parameter names.

Auto-discovery algorithm:
1. Group both sides (preset keys, plugin params) by prefix
2. Match groups by overlapping suffixes
3. Handle special patterns: EQ bands, cab L/R, room L/R, per-amp mic types
4. Apply well-known renames and direct snake_case conversion

Result: ~159 of ~170 params mapped automatically, no per-plugin config needed.

### `refinement.py` — Refinement System

Parses delta commands for stateful tone modification. Uses a dedicated refinement textbox in the UI (enabled after a tone is loaded), so there is no keyword-based mode detection.

`parse_deltas`: maps ~30 tone keywords and comparative adjectives to canonical param deltas with direction weights. Supports magnitude modifiers ("a bit less", "way more") and applies `difflib` fuzzy matching for typo tolerance ("crhnchy" → "crunchy").

### `app.py` — Gradio App

Real-time audio streaming via pedalboard's `AudioStream`. Handles:
- Audio device selection and streaming
- Plugin loading/swapping (main-thread loader queue for VST3/Cocoa compatibility)
- **Two separate textboxes**: search (always active) and refine (enabled only after a tone is loaded)
- Top-5 selection, raw preset loading, raw preset blending

## Extension Points

### Adding a new Neural DSP plugin
Only requires config additions — no logic changes. See [adding-plugins.md](adding-plugins.md).

### Swapping DSP backend
Replace `adapter.py` and `preset_loader.py`. The NLP engine, canonical schema, and refinement system are backend-agnostic.

### Improving NLP
The embedding model, matching algorithm, and description generation can all be upgraded independently of the DSP layer. The anchor database format (`data/anchors.yaml`) is the stable interface.

### Enriching descriptions
The current `_describe_tone()` in `anchor_builder.py` derives its output from the adapter's measured canonical values. To add new description dimensions, extend `_describe_tone()` — but only with things the adapter can actually measure, not hand-guessed style labels.

## Threading Model

VST3 plugins on macOS require the main (Cocoa) thread for initialization. Gradio runs callbacks in worker threads. The solution:

```
Main thread:   _main_thread_loader_loop()  ←── polls queue
                      ↑
Worker thread: search_tone() → posts (plugin_path, event) to queue → waits
                      ↑
Gradio:        runs in background (prevent_thread_lock=True)
```

This allows unlimited plugin swapping without resource leaks.
