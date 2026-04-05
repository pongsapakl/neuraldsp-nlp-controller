# Acoustic Fingerprint Retrieval — Exploration Note

**Date:** 2026-04-05
**Status:** Deferred (open exploration, not blocked)
**Related decision:** `docs/decisions/2026-04-05-v1-clean-no-coverage-no-llm.md`

---

## The Idea

Instead of matching text queries against text descriptions of presets, match against **audio fingerprints** of what each preset actually sounds like.

```
Current V1:
  "warm clean with reverb" ──→ text embed ──→ cosine vs preset name+description embeddings ──→ preset

Fingerprint V2:
  "warm clean with reverb" ──→ ???       ──→ audio feature space ──→ preset
  audio_clip.wav          ──→ features ──→ audio feature space ──→ preset
```

The appeal: text descriptions are our bottleneck. Even with honest canonical descriptions, they only capture what the adapter can measure — not the actual timbre the guitarist hears. A fingerprint is "ground truth" in the only sense that matters: the audio itself.

## Why this is interesting

### 1. It bypasses the labeling problem
We spent a whole session discovering we can't hand-label "Vox-style crunch" honestly. If the match is done in audio-feature space, we never need style labels at all. The preset's actual frequency content is its label.

### 2. It unlocks audio-to-audio search
A guitarist hears a tone in a song and wants *that*. Today they'd have to translate the tone into words ("bright, chimey, slight overdrive, slapback"), then hope the text lands in the right embedding neighborhood. With fingerprinting, they upload a 5-second clip — or even play a few seconds through the interface — and the system finds the nearest presets by sound.

### 3. It couples naturally with "sound from internet" workflows
If V-something integrates with an online sound source (SoundCloud tag, YouTube clip, Splice loop), the pipeline is uniform: whatever audio comes in, extract features, query the same index. Text queries become just one of several input modes.

### 4. It makes gap detection real
If the nearest fingerprint match is still far away in feature space, we can say "your library has no preset that sounds like this" with mathematical confidence — which is exactly the gap-visibility property we wanted from the failed coverage anchors.

## What would need to exist

### a. Rendering pipeline
For each preset, render a fixed test signal (DI guitar clip, impulse, frequency sweep, or a mix) through the VST3 and capture the audio output.

- Test signal choice matters a lot. A single chord won't capture gain behavior; a sweep won't capture transient response; a full DI clip is slow but realistic.
- Rendering runs offline in the same `build_anchor_db.py` pipeline — ~422 presets × N seconds each, probably once per plugin library.

### b. Feature extraction
Transform each rendered clip into a fixed-dimensional feature vector. Candidates:

- **MFCC** (mel-frequency cepstral coefficients) — classical audio ID, works for timbre similarity
- **Mel-spectrogram + CNN embedding** — richer, but needs a pretrained model (YAMNet, VGGish, CLAP)
- **CLAP embeddings** — joint text-audio space, would let us query with text **and** audio against the same index. This is probably the most interesting direction because it preserves the text query path while unlocking audio queries.
- **Handcrafted features** (spectral centroid, flux, rolloff, zero-crossing rate, RMS, harmonic ratio) — interpretable, debuggable, lightweight

First experiment: try CLAP. If it's too heavy, fall back to MFCC + handcrafted stats.

### c. Distance metric
Cosine or Euclidean in the feature space. Needs to be **perceptually meaningful** — two clips that sound similar to a human should be close. This is why pretrained audio models beat handcrafted features in practice.

### d. A benchmark
Before spending real time on this, we need a concrete test: given a text query and a held-out preset, does audio-feature retrieval find the preset better than the current text retrieval? Without a benchmark this is infinite tinkering.

## Why deferred

1. **V1 had to ship.** Preset-only text retrieval works well enough for the pain points we care about (see README). Perfect is the enemy of done.
2. **Rendering is slow.** 422 presets × 10s of audio × 2 plugins = ~2 hours of VST3 rendering. Not a blocker, but needs to be a separate one-time script.
3. **Feature choice is open.** We don't yet know if CLAP is fast enough on a laptop, and we don't have a baseline to compare alternatives against.
4. **No benchmark dataset exists.** We'd need to hand-label a small "query → expected preset" set to evaluate anything, and that labeling is the same expertise problem that killed the semantic extractor.
5. **Rendering the test signal is its own research project.** DI clip? Sweep? What guitar? What playing style? The choice biases every downstream result.

## When to revisit

Trigger conditions:

- V1 ships, gets real usage, and users report "I can't find the tone I'm hearing" more than they report "I can't search for this word". That signals text is the bottleneck.
- Someone integrates a "sound from internet" or "upload a clip" feature request. Fingerprinting becomes load-bearing, not optional.
- A pretrained joint text-audio model (CLAP successor, Audio-Text contrastive checkpoints) appears that runs comfortably on laptop CPU. This would make the text path free and the audio path a bolt-on.
- We hit a plateau in text retrieval quality that more descriptions can't fix.

## First concrete experiment (when we pick this up)

1. Pick 10 presets spanning character extremes (clean → chug → lead → ambient).
2. Render each through the VST3 with a single DI guitar clip (5 seconds).
3. Extract MFCC + CLAP embeddings for each.
4. Hand-write 10 text queries, one per preset.
5. For each query: rank the 10 presets by (a) current text retrieval, (b) CLAP text-audio, (c) MFCC distance from a reference "query rendering".
6. See which wins.

This is a one-afternoon spike. If (b) or (c) beats (a), we have an argument to fund the full build.

## Not in scope of this note

- LLM-based param generation (rejected — see decision doc).
- Replacing the retrieval index format (still `data/anchors.yaml`, audio features can sit next to the text description).
- UI for audio upload — that's a later concern.

## One-liner to remember

> "We label honestly in V1 and measure honestly in V2. Fingerprinting is the measurement upgrade."
