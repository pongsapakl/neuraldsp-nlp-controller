"""NLP engine — maps text descriptions to canonical tones via embeddings.

Uses sentence-transformers for embedding + cosine similarity against the
anchor database. Same mathematical approach as 1P.

Usage:
  engine = NLPEngine("data/anchors.yaml")
  matches = engine.query("warm blues crunch")
  # matches[0] = {"description": "...", "tone": {...}, "score": 0.87, ...}
"""

import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer

from .anchor_builder import load_anchors
from .canonical import CanonicalTone, Amp, Overdrive, Compressor, Chorus, Delay, Reverb


# Same model as 1P — fast, good for short descriptions
DEFAULT_MODEL = "all-MiniLM-L6-v2"


class NLPEngine:
    """Embedding-based NLP engine for tone matching."""

    def __init__(self, anchor_path: str | Path, model_name: str = DEFAULT_MODEL):
        self.anchors = load_anchors(anchor_path)
        self.model = SentenceTransformer(model_name)
        self._build_index()

    def _build_index(self):
        """Embed all anchor descriptions and cache."""
        descriptions = [a["description"] for a in self.anchors]
        self.embeddings = self.model.encode(descriptions, normalize_embeddings=True)

    def query(self, text: str, top_k: int = 5) -> list[dict]:
        """Find the closest anchors to a text description.

        Returns list of dicts with keys: description, tone, score,
        plugin_name, preset_name, preset_path.
        """
        q_emb = self.model.encode([text], normalize_embeddings=True)
        scores = (q_emb @ self.embeddings.T)[0]
        top_indices = np.argsort(scores)[::-1][:top_k]

        results = []
        for idx in top_indices:
            result = dict(self.anchors[idx])
            result["score"] = float(scores[idx])
            results.append(result)
        return results

    def match(self, text: str) -> tuple[CanonicalTone, dict]:
        """Find the single best matching tone for a text description.

        Returns (CanonicalTone, match_info) where match_info has
        score, description, plugin_name, preset_name.
        """
        results = self.query(text, top_k=1)
        best = results[0]
        tone = _dict_to_tone(best["tone"])
        tone.plugin_name = best["plugin_name"]
        tone.preset_name = best["preset_name"]
        info = {
            "score": best["score"],
            "description": best["description"],
            "plugin_name": best["plugin_name"],
            "preset_name": best["preset_name"],
        }
        return tone, info


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
