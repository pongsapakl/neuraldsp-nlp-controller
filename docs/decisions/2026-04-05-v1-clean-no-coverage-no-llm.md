# V1 Clean: Preset-Only Anchors, No LLM, No Synthetic Coverage

**Date:** 2026-04-05
**Status:** Accepted
**Applies to:** NeuralDSP NLP Controller V1 (the OSS release)

---

## Context

Between Phase 2.1 and this session, the project accumulated three experiments that all ran together:

1. **Semantic extractor** (`semantic_extractor.py`) — read raw plugin params and emitted hand-authored tags like "Vox-style crunch", "Fender-style clean", "British", "chimey", "dynamic mic punch".
2. **Coverage anchors** (`generate_coverage_anchors.py`) — 40 synthetic anchors generated from a `_PLUGIN_SEMANTICS` config dict, to "fill gaps" the factory presets didn't cover.
3. **Single-textbox UX** — one input for search AND refinement, with `is_refinement()` keyword detection deciding the mode.

After end-to-end testing the user hit multiple problems at once and we paused to redesign.

### Problems observed

| # | Problem | Root cause |
|---|---|---|
| 1 | Clean presets described as "crushing" / "very high gain" | `semantic_extractor._gain_tags()` used `(val - mn)/(mx - mn)` against `param.min_value/max_value` (0–1) but `getattr(plugin, pb_name)` returns raw knob values. Normalization math was wrong. |
| 2 | "Vox amp doesn't sound Vox" | I had hand-authored `_PLUGIN_SEMANTICS` mapping `Cherubs → Vox-style, chimey` without A/B-listening. They were guesses, not measurements. Honest measurement is not something this pipeline could produce. |
| 3 | Coverage anchors dominate top-K | Short synthetic anchor text ("overdrive pedal") embeds closer to short keyword queries than long preset descriptions, polluting results. |
| 4 | Coverage anchors cannot blend | They have no `preset_path`, so `blend_presets()` silently drops them — user clicks "Blend All" and the coverage hit is ignored. |
| 5 | Duplicate coverage anchor names | Multiple coverage entries labeled "overdrive" with internally-different params — UI can't distinguish them. |
| 6 | Search vs refinement confusion | `is_refinement()` guessed mode from keyword prefixes. Invisible to the user, fragile ("more crunchy" → refine, "crunchy" → search). |
| 7 | Typos killed refinement | Substring matching in `parse_deltas()` — "more crhnchy" failed silently with a generic error. |

### Competing proposals

After diagnosing the above, two directions were on the table:

- **A. Full LLM pipeline** — use an LLM to generate canonical param values directly from free text, bypassing embeddings.
- **B. Acoustic fingerprint retrieval** — render each preset to audio, extract features (MFCC, spectral centroid, etc.), and retrieve by audio similarity instead of text similarity.

## Decision

**Rip out the semantic extractor, coverage anchors, and single-textbox UX. Ship V1 as a preset-only retrieval system with honest canonical descriptions. Reject LLM. Defer fingerprinting.**

Concretely, V1 Clean:

- Anchors = factory presets only (~422), no synthetic entries.
- Description = preset name + canonical values the adapter actually measured (character, gain bin, EQ shape, active effects).
- Refinement lives in a **separate** textbox, enabled only after a tone is applied.
- `parse_deltas()` uses `difflib` fuzzy matching on the last token (cutoff 0.75) for typo tolerance.
- No `semantic_extractor.py`, no `generate_coverage_anchors.py`, no `_PLUGIN_SEMANTICS`.

## Why (grouped by principle)

### 1. Honest measurement > plausible-sounding labels

Every description must trace to a value the adapter read from the loaded plugin. If we can't measure it, we don't claim it. "Vox-style" requires A/B listening expertise we don't have — shipping it as a tag is misinformation, and the embedding space rewards the misinformation by matching "Vox" queries to presets we never verified.

The canonical-only descriptions are blander, but they are **true**. A future iteration can enrich them only by adding new measurements to the adapter, not by adding a guess table.

### 2. Rejecting the LLM path — this must stay mathematical, local, and reusable

The LLM proposal was rejected because it breaks the product thesis. Quote from the session:

> "if so why not let ai-agent do the music for you. to me it seems like it cqan be just claude code on top of logic pro? this one i think we should focus on mathematical approach where it provide a reusable and low-resource-usage"

Principles locked in:

- **Local-first** — a tone controller that needs a network call per query is not a guitar tool, it's a web app with latency.
- **Reusable** — the engine should drop onto any DSP backend (Neural DSP today, NAM, custom). An LLM trained on one plugin's param names doesn't transfer.
- **Low resource** — it has to run on the same laptop as a DAW + VST3 + real-time audio. Sentence-transformers (~80MB, CPU, milliseconds) fits. A 7B+ LLM does not.
- **Deterministic** — same query should return the same preset. LLM sampling noise is a footgun for a live instrument.
- **Not an AI music agent** — the product is "type tone, play guitar faster". If we let the AI play the guitar, there is no product.

If the value proposition ever shifts to "AI makes music for you", a different project should be started — not a pivot of this one.

### 3. Coverage anchors solved the wrong problem

Coverage anchors were meant to fill retrieval gaps — i.e. "we don't have a preset that matches 'shimmer reverb', so let's fabricate one". But:

- If the preset library genuinely lacks a tone, **the retrieval should show that gap**, not hide it behind a synthetic match. The user learns their library has holes and the product learns what to add.
- Coverage anchors that can't be loaded (no `preset_path`) are a dead end — the user clicks the match and gets nothing useful.
- The ranking pollution (problem #3) is unfixable without downweighting synthetic entries, at which point they stop "covering" anything.

The honest answer is: V1 ships with whatever coverage the user's legally-owned factory presets give. If that's insufficient, the fix is to add more presets (or a different plugin), not more fake anchors.

### 4. UX must make mode explicit

Keyword-based mode detection is a feature that's invisible until it's wrong. Two textboxes cost nothing and make the model obvious: box 1 searches, box 2 refines. Refinement is gated on `state.tone_loaded` so there's no confused state where refine fires before a tone exists.

### 5. Refinement fuzzy-matching is the minimum viable polish

The refinement vocabulary is ~60 words. It will never cover everything a guitarist thinks. But ~80% of failures in testing were typos on words we already know — so `difflib.get_close_matches()` on the last token (cutoff 0.75) recovers most of them at zero cost. We chose the last token because that's where tone words sit in phrases like "a bit more crhnchy".

## Rejected Alternatives

### A. Full LLM pipeline

Rejected in full. See "Why #2" above. An LLM is welcome for orchestrating the agent-level product (if we ever build one), but not for the DSP layer.

### B. Acoustic fingerprint retrieval

**Deferred**, not rejected. See `docs/research/2026-04-05-acoustic-fingerprint-exploration.md`. The idea is promising for two reasons:

1. It solves the "described vs actual sound" gap — embeddings of text descriptions inherit our description quality; embeddings of rendered audio inherit the plugin's actual output.
2. It would let users search by **audio example** ("find a preset that sounds like this song clip"), which is closer to how guitarists already think about tone.

Why deferred: requires rendering every preset through the VST3 at build time (slow, per-plugin), requires a feature-extraction pipeline that doesn't exist yet, and requires a perceptually meaningful distance metric we haven't chosen. V1 has to ship before we take that on.

### C. Fixing the semantic extractor in place

Rejected. The gain normalization bug was fixable in an hour, but the deeper issue — hand-authored style tags — was unfixable without domain-expert labeling, which we don't have budget for. Cleaning up broken labels produces boring true labels, and boring true labels are already what the canonical description does.

### D. Keeping coverage anchors but downweighting them in ranking

Rejected. Downweighting means they rarely win, which means they rarely fire, which means they provide no coverage. The only way they'd be visible is if they actually got selected — and if they get selected, they pollute the results.

## Consequences

### Positive

- Anchor DB is smaller (422 vs 462), faster to load.
- Descriptions are honest — future bugs are detectable by comparing text to reality.
- No per-plugin semantic config → adding a new plugin is adapter work only.
- UX is explicit and predictable.
- The codebase is ~2600 lines smaller.

### Negative

- Descriptions are blander. Queries like "warm vintage Vox crunch" no longer hit style tags — they match only on the parts the adapter measures (gain, EQ, effects).
- Coverage gaps are visible. If the user's preset library has no shimmer reverb, the top-5 for "shimmer" will be the 5 closest presets, none of which will actually shimmer. This is by design but it is a worse experience than the fake-coverage version would have implied.
- Refinement remains a closed vocabulary. No new words work unless we add them to `_KEYWORDS`.

### Open Questions Deferred

- Do we need a way to tell users "your library doesn't cover this" instead of silently returning the closest-but-wrong matches?
- Should `_describe_tone()` grow richer canonical-derived descriptors? (Yes, but only if the adapter can measure them — e.g. delay time buckets, compressor attack bucket, reverb size bucket.)
- Acoustic fingerprint exploration — see research note.

## Files Touched (V1 Clean migration)

Deleted:
- `src/neuraldsp_nlp_controller/semantic_extractor.py`
- `scripts/generate_coverage_anchors.py`
- `scripts/add_pure_effect_anchors.py`
- `data/anchors.example.yaml`

Modified:
- `src/neuraldsp_nlp_controller/anchor_builder.py` — `_describe_tone()` simplified to canonical-only
- `src/neuraldsp_nlp_controller/refinement.py` — removed `is_refinement()`, added `recognized_keywords()`, `suggest_keyword()`, fuzzy fallback in `parse_deltas()`
- `app.py` — split search/refine UI, removed canonical-fallback paths in `apply_choice` / `apply_blended`
- `scripts/build_anchor_db.py` — preset-only pipeline
- `README.md`, `docs/architecture.md`, `docs/adding-plugins.md`, `.claude/CLAUDE.md`

## Verification

- `grep -c "^- description:" data/anchors.yaml` → 422
- `grep -i "vox\|fender\|crushing" data/anchors.yaml` → empty
- Live test: search, apply, refine with typo ("more crhnchy") — all work, user confirmed "lovely" and "refinement is perfect".

## Revisit Conditions

Re-open this decision **only** if:

- A measurable, non-guessed enrichment source appears (e.g. a plugin exposes genuine style metadata).
- Acoustic fingerprinting is prototyped and outperforms preset-name retrieval on a concrete benchmark.
- The value proposition changes away from "local, fast, deterministic preset retrieval" — at which point this is probably a different project.
