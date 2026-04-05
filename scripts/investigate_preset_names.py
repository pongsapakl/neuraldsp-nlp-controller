"""Investigate: do preset names help or hurt NLP matching?

A/B test: compare query results with full descriptions (name + params)
vs param-only descriptions (no preset name).

Usage:
  uv run python scripts/investigate_preset_names.py
"""

import yaml
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer

ANCHOR_PATH = Path(__file__).parent.parent / "data" / "anchors.yaml"

# Test queries spanning different tone categories
QUERIES = [
    # Basic tones
    "warm blues crunch",
    "modern metal djent",
    "clean funk sparkle",
    "80s chorus clean",
    "ambient shimmer",
    "classic rock crunch",
    "jazz clean warm",
    "heavy distortion palm mute",
    # Effect-focused
    "reverb spacious hall",
    "slapback delay rockabilly",
    "chorus wide stereo",
    "overdrive tube screamer",
    # Descriptive (should match param-derived text well)
    "bright clean low gain",
    "dark heavy saturated",
    "mid scooped high gain",
    "compressed clean funk",
    # Edge cases (artisanal-ish queries)
    "dreamy atmospheric",
    "aggressive tight rhythm",
    "smooth singing lead",
    "lo-fi warm tape",
]


def main():
    with open(ANCHOR_PATH) as f:
        anchors = yaml.safe_load(f)

    # Separate factory from pure anchors
    factory = [a for a in anchors if not a.get("preset_name", "").startswith("[Pure]")]
    print(f"Factory anchors: {len(factory)}")

    # Build two description sets
    full_descs = [a["description"] for a in factory]
    # Strip preset name (first token before first comma)
    param_only_descs = []
    for a in factory:
        desc = a["description"]
        # Remove preset name — everything before first comma
        parts = desc.split(", ", 1)
        param_only_descs.append(parts[1] if len(parts) > 1 else desc)

    # Embed both
    print("Loading model...")
    model = SentenceTransformer("all-MiniLM-L6-v2")

    print("Embedding full descriptions...")
    full_embeds = model.encode(full_descs, normalize_embeddings=True)
    print("Embedding param-only descriptions...")
    param_embeds = model.encode(param_only_descs, normalize_embeddings=True)

    print("\n" + "=" * 90)
    print(f"{'QUERY':<35} {'FULL (name+params)':<30} {'PARAM-ONLY':<30}")
    print("=" * 90)

    score_diffs = []
    rank_changes = 0
    better_with_name = 0
    better_without_name = 0

    for query in QUERIES:
        q_embed = model.encode([query], normalize_embeddings=True)

        # Full description scores
        full_scores = (full_embeds @ q_embed.T).flatten()
        full_top_idx = np.argmax(full_scores)
        full_top_name = factory[full_top_idx]["preset_name"]
        full_top_score = full_scores[full_top_idx]

        # Param-only scores
        param_scores = (param_embeds @ q_embed.T).flatten()
        param_top_idx = np.argmax(param_scores)
        param_top_name = factory[param_top_idx]["preset_name"]
        param_top_score = param_scores[param_top_idx]

        # Compare
        changed = "  " if full_top_idx == param_top_idx else "!!"
        print(f"{query:<35} {full_top_name[:25]:<25} {full_top_score:.3f}  "
              f"{param_top_name[:25]:<25} {param_top_score:.3f}  {changed}")

        if full_top_idx != param_top_idx:
            rank_changes += 1

        score_diffs.append(param_top_score - full_top_score)

    print("=" * 90)
    print(f"\nResults changed in {rank_changes}/{len(QUERIES)} queries")
    print(f"Avg score diff (param_only - full): {np.mean(score_diffs):+.4f}")
    print(f"  Positive = param-only scores higher (names hurt)")
    print(f"  Negative = full scores higher (names help)")

    # Deeper analysis: how many presets have descriptive vs artisanal names?
    print("\n" + "=" * 90)
    print("PRESET NAME ANALYSIS")
    print("=" * 90)

    # Simple heuristic: if preset name contains tone-related words, it's descriptive
    tone_words = {"clean", "crunch", "lead", "metal", "blues", "funk", "jazz",
                  "acoustic", "ambient", "chorus", "delay", "reverb", "overdrive",
                  "distortion", "warm", "bright", "dark", "heavy", "light",
                  "rhythm", "solo", "boost", "drive", "gain", "comp"}

    descriptive = 0
    artisanal = 0
    for a in factory:
        name_lower = a["preset_name"].lower()
        if any(w in name_lower for w in tone_words):
            descriptive += 1
        else:
            artisanal += 1

    print(f"Descriptive names (contain tone words): {descriptive} ({100*descriptive/len(factory):.0f}%)")
    print(f"Artisanal names (creative/abstract):    {artisanal} ({100*artisanal/len(factory):.0f}%)")

    # Show some artisanal names
    artisanal_names = [a["preset_name"] for a in factory
                       if not any(w in a["preset_name"].lower() for w in tone_words)]
    print(f"\nSample artisanal names ({len(artisanal_names)} total):")
    for name in artisanal_names[:20]:
        print(f"  {name}")

    # Test: do artisanal names ever win because the name matches the query?
    print("\n" + "=" * 90)
    print("NAME-DRIVEN MATCHES (query word appears in preset name)")
    print("=" * 90)
    for query in QUERIES:
        q_words = set(query.lower().split())
        q_embed = model.encode([query], normalize_embeddings=True)
        full_scores = (full_embeds @ q_embed.T).flatten()
        top5 = np.argsort(full_scores)[::-1][:5]
        for idx in top5:
            name = factory[idx]["preset_name"].lower()
            overlap = q_words & set(name.split())
            if overlap:
                print(f"  '{query}' → #{np.where(top5 == idx)[0][0]+1} "
                      f"'{factory[idx]['preset_name']}' (shared: {overlap})")


if __name__ == "__main__":
    main()
