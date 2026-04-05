"""NLP engine — maps text descriptions to canonical tones via embeddings.

Uses sentence-transformers for embedding + cosine similarity against the
anchor database, then interpolates top-K matches using exponential-decay
weighting (same approach as 1P's ParameterInterpolator).

Usage:
  engine = NLPEngine("data/anchors.yaml")
  tone, info = engine.match("warm blues crunch", plugin_name="Archetype Tim Henson X")
"""

import math
from dataclasses import fields

import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer

from .anchor_builder import load_anchors
from .canonical import CanonicalTone, Amp, Overdrive, Compressor, Chorus, Delay, Reverb


# Same model as 1P — fast, good for short descriptions
DEFAULT_MODEL = "all-MiniLM-L6-v2"

# Continuous (interpolatable) fields per canonical section
_CONTINUOUS_FIELDS = {
    "overdrive": ["drive", "tone", "level"],
    "compressor": ["attack", "release", "compression"],
    "amp": ["gain", "bass", "mid", "treble", "presence", "master", "output"],
    "chorus": ["rate", "depth", "mix"],
    "delay": ["time", "feedback", "mix"],
    "reverb": ["size", "damping", "mix"],
}

# Discrete fields — taken from the highest-weighted anchor, not blended
_DISCRETE_FIELDS = {
    "overdrive": ["active"],
    "compressor": ["active"],
    "amp": ["character"],
    "chorus": ["active"],
    "delay": ["active"],
    "reverb": ["active"],
}


class NLPEngine:
    """Embedding-based NLP engine for tone matching with interpolation."""

    def __init__(self, anchor_path: str | Path, model_name: str = DEFAULT_MODEL):
        self.anchors = load_anchors(anchor_path)
        self.model = SentenceTransformer(model_name)
        self._build_index()

    def _build_index(self):
        """Embed all anchor descriptions and cache."""
        descriptions = [a["description"] for a in self.anchors]
        self.embeddings = self.model.encode(descriptions, normalize_embeddings=True)

    def query(self, text: str, top_k: int = 5,
              plugin_name: str | None = None) -> list[dict]:
        """Find the closest anchors to a text description.

        Args:
            text: User's tone description.
            top_k: Number of results to return.
            plugin_name: If set, only search anchors from this plugin.

        Returns list of dicts with keys: description, tone, score,
        plugin_name, preset_name, preset_path.
        """
        q_emb = self.model.encode([text], normalize_embeddings=True)
        scores = (q_emb @ self.embeddings.T)[0]

        # Filter by plugin if requested (empty plugin_name = universal anchor)
        if plugin_name:
            for i, anchor in enumerate(self.anchors):
                if anchor["plugin_name"] and anchor["plugin_name"] != plugin_name:
                    scores[i] = -1.0  # exclude

        top_indices = np.argsort(scores)[::-1][:top_k]

        results = []
        for idx in top_indices:
            if scores[idx] < 0:
                break  # all remaining are excluded
            result = dict(self.anchors[idx])
            result["score"] = float(scores[idx])
            results.append(result)
        return results

    def match(self, text: str, top_k: int = 5, sensitivity: float = 1.0,
              plugin_name: str | None = None) -> tuple[CanonicalTone, dict]:
        """Find and interpolate the best matching tone.

        Uses 1P-style exponential-decay interpolation across top-K matches:
        1. Find top-K anchors by cosine similarity
        2. Compute weights: w = exp(-(1 - similarity) * sensitivity)
        3. Blend continuous params (gain, bass, mix, etc.) by weighted average
        4. Take discrete params (character, active) from highest-weighted anchor

        Args:
            text: User's tone description.
            top_k: Number of anchors to blend (default 5).
            sensitivity: Blending sharpness (default 1.0).
                Higher (e.g. 5.0) = favor top match, nearly exact preset.
                Lower (e.g. 0.5) = blend more evenly, smoother gradients.
            plugin_name: If set, only search anchors from this plugin.

        Returns (CanonicalTone, match_info).
        """
        results = self.query(text, top_k=top_k, plugin_name=plugin_name)
        if not results:
            return CanonicalTone(), {"score": 0, "description": "no match",
                                     "plugin_name": "", "preset_name": ""}

        if len(results) == 1:
            return _result_to_tone(results[0])

        tone = _interpolate(results, sensitivity)
        best = results[0]
        info = {
            "score": best["score"],
            "description": best["description"],
            "plugin_name": best["plugin_name"],
            "preset_name": best["preset_name"],
            "interpolated_from": len(results),
            "top_matches": [
                {"preset": r["preset_name"], "score": r["score"]}
                for r in results
            ],
        }
        return tone, info


def _result_to_tone(result: dict) -> tuple[CanonicalTone, dict]:
    """Convert a single query result to (CanonicalTone, info)."""
    tone = _dict_to_tone(result["tone"])
    tone.plugin_name = result["plugin_name"]
    tone.preset_name = result["preset_name"]
    info = {
        "score": result["score"],
        "description": result["description"],
        "plugin_name": result["plugin_name"],
        "preset_name": result["preset_name"],
    }
    return tone, info


def _interpolate(results: list[dict], sensitivity: float) -> CanonicalTone:
    """Blend top-K canonical tones using exponential-decay weighting.

    Same algorithm as 1P's ParameterInterpolator:
    - distance = 1 - similarity
    - weight = exp(-distance * sensitivity)
    - continuous params = weighted average
    - discrete params = from top match
    """
    # Compute normalized weights
    weights = []
    for r in results:
        distance = 1.0 - r["score"]
        weights.append(math.exp(-distance * sensitivity))
    total = sum(weights)
    weights = [w / total for w in weights]

    tones = [r["tone"] for r in results]

    # Start from top match (discrete fields come from here)
    blended = _deep_copy_tone_dict(tones[0])

    # Blend continuous fields
    for section, cont_fields in _CONTINUOUS_FIELDS.items():
        for field_name in cont_fields:
            val = sum(w * t[section][field_name] for w, t in zip(weights, tones))
            blended[section][field_name] = max(0.0, min(1.0, val))

    tone = _dict_to_tone(blended)
    tone.plugin_name = results[0]["plugin_name"]
    tone.preset_name = results[0]["preset_name"]
    return tone


def _deep_copy_tone_dict(d: dict) -> dict:
    """Deep copy a tone dict (one level of nesting)."""
    return {k: dict(v) if isinstance(v, dict) else v for k, v in d.items()}


def _dict_to_tone(d: dict) -> CanonicalTone:
    """Convert anchor tone dict back to CanonicalTone dataclass."""
    return CanonicalTone(
        overdrive=Overdrive(**d["overdrive"]),
        compressor=Compressor(**d["compressor"]),
        amp=Amp(**d["amp"]),
        chorus=Chorus(**d["chorus"]),
        delay=Delay(**d["delay"]),
        reverb=Reverb(**d["reverb"]),
    )
