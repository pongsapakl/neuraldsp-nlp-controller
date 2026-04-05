"""Stateful iterative refinement — parse delta commands into parameter adjustments.

Parses natural-language refinement commands ("less fizzy", "brighter",
"more gain") into canonical parameter deltas that can be applied to the
current plugin state via adapter.apply_delta().

Usage:
  from neuraldsp_nlp_controller.refinement import parse_deltas

  deltas = parse_deltas("less fizzy")
  # → {"amp.treble": -0.1, "amp.presence": -0.1}
"""

import difflib

DELTA_STEP = 0.1

# Maps tone keywords → canonical params with direction (+1 = more, -1 = less)
_KEYWORDS = {
    # Brightness / harshness
    "fizzy":    {"amp.treble": -1, "amp.presence": -1},
    "harsh":    {"amp.treble": -1, "amp.presence": -1},
    "bright":   {"amp.treble": 1, "amp.presence": 1},
    "dark":     {"amp.treble": -1, "amp.presence": -1, "amp.bass": 0.5},
    "sparkle":  {"amp.treble": 1, "amp.presence": 0.5},

    # Warmth
    "warm":     {"amp.bass": 0.5, "amp.mid": 0.5, "amp.treble": -0.5},
    "warmth":   {"amp.bass": 0.5, "amp.mid": 0.5, "amp.treble": -0.5},
    "cold":     {"amp.bass": -0.5, "amp.treble": 0.5},

    # Gain / drive
    "gain":     {"amp.gain": 1},
    "drive":    {"amp.gain": 0.5, "overdrive.drive": 1},
    "saturation": {"amp.gain": 1},
    "clean":    {"amp.gain": -1},
    "heavy":    {"amp.gain": 1},
    "crunch":   {"amp.gain": 0.7},

    # Low end
    "bass":     {"amp.bass": 1},
    "mud":      {"amp.bass": -1, "amp.mid": -0.3},
    "muddy":    {"amp.bass": -1, "amp.mid": -0.3},
    "tight":    {"amp.bass": -0.7, "amp.mid": 0.3},
    "loose":    {"amp.bass": 0.7},
    "boomy":    {"amp.bass": -1},
    "thin":     {"amp.bass": 0.5, "amp.mid": 0.3},

    # Mids
    "mid":      {"amp.mid": 1},
    "mids":     {"amp.mid": 1},
    "scoop":    {"amp.mid": -1},
    "scooped":  {"amp.mid": -1},
    "nasal":    {"amp.mid": -1},
    "honky":    {"amp.mid": -1},
    "full":     {"amp.mid": 0.5, "amp.bass": 0.3},

    # Effects — mix/intensity
    "reverb":   {"reverb.mix": 1},
    "wet":      {"reverb.mix": 0.7, "delay.mix": 0.5},
    "dry":      {"reverb.mix": -1, "delay.mix": -1},
    "delay":    {"delay.mix": 1},
    "echo":     {"delay.mix": 1, "delay.feedback": 0.5},
    "chorus":   {"chorus.mix": 1},
    "wide":     {"chorus.mix": 0.7, "chorus.depth": 0.7},
    "narrow":   {"chorus.mix": -0.7, "chorus.depth": -0.7},
    "compressed": {"compressor.compression": 1},
    "compression": {"compressor.compression": 1},
    "dynamic":  {"compressor.compression": -1},
    "overdrive": {"overdrive.drive": 1},
    "boost":    {"overdrive.level": 1},

    # Presence / output
    "presence": {"amp.presence": 1},
    "volume":   {"amp.output": 1},
    "loud":     {"amp.output": 1},
    "quiet":    {"amp.output": -1},
}

# Comparative adjectives — already have direction built in
_COMPARATIVES = {
    "brighter":  {"amp.treble": 1, "amp.presence": 0.5},
    "darker":    {"amp.treble": -1, "amp.presence": -0.5, "amp.bass": 0.3},
    "warmer":    {"amp.bass": 0.5, "amp.mid": 0.5, "amp.treble": -0.5},
    "cooler":    {"amp.bass": -0.3, "amp.treble": 0.3},
    "heavier":   {"amp.gain": 1},
    "lighter":   {"amp.gain": -1},
    "tighter":   {"amp.bass": -0.7, "amp.mid": 0.3},
    "looser":    {"amp.bass": 0.7},
    "wetter":    {"reverb.mix": 0.7, "delay.mix": 0.5},
    "drier":     {"reverb.mix": -1, "delay.mix": -0.7},
    "cleaner":   {"amp.gain": -1, "overdrive.drive": -0.5},
    "muddier":   {"amp.bass": 1, "amp.mid": -0.5},
    "thicker":   {"amp.bass": 0.5, "amp.mid": 0.3, "amp.gain": 0.3},
    "thinner":   {"amp.bass": -0.5, "amp.mid": -0.3},
    "fuller":    {"amp.mid": 0.5, "amp.bass": 0.3},
    "sharper":   {"amp.treble": 1, "amp.presence": 1},
    "smoother":  {"amp.treble": -0.5, "amp.presence": -0.5},
    "crunchier": {"amp.gain": 0.7},
    "wider":     {"chorus.mix": 0.7, "chorus.depth": 0.5},
}

_DIRECTION_PREFIXES = {
    "more ": 1.0,
    "add ": 1.0,
    "increase ": 1.0,
    "less ": -1.0,
    "reduce ": -1.0,
    "decrease ": -1.0,
    "remove ": -2.0,
    "cut ": -1.0,
    "drop ": -1.0,
}

_MAGNITUDE_MODIFIERS = {
    "a bit": 0.5,
    "slightly": 0.5,
    "a little": 0.5,
    "a touch": 0.5,
    "much": 2.0,
    "way": 2.0,
    "a lot": 2.0,
    "way more": 2.5,
    "way less": 2.5,
}


def recognized_keywords() -> list[str]:
    """Return the full list of recognized tokens (keywords + comparatives)."""
    return list(_KEYWORDS.keys()) + list(_COMPARATIVES.keys())


def suggest_keyword(token: str, cutoff: float = 0.75) -> str | None:
    """Return the nearest recognized keyword to `token`, or None if no close match."""
    matches = difflib.get_close_matches(
        token.lower(), recognized_keywords(), n=1, cutoff=cutoff
    )
    return matches[0] if matches else None


def parse_deltas(text: str) -> dict[str, float]:
    """Parse a refinement command into {canonical_param: delta_value}.

    Positive delta = increase, negative = decrease.
    Delta magnitude is DELTA_STEP (0.1) by default, scaled by modifiers.
    Applies simple fuzzy matching: unknown tokens get replaced by their
    nearest recognized keyword if similarity > 0.75 (typo tolerance).
    """
    t = text.lower().strip()

    # Determine direction from prefix
    direction = 1.0
    for prefix, d in _DIRECTION_PREFIXES.items():
        if t.startswith(prefix):
            direction = d
            break

    # Determine magnitude from modifiers
    magnitude = DELTA_STEP
    for mod, scale in _MAGNITUDE_MODIFIERS.items():
        if mod in t:
            magnitude *= scale
            break

    deltas: dict[str, float] = {}

    # Check comparatives first (they carry their own direction)
    for comp, params in _COMPARATIVES.items():
        if comp in t:
            for param, weight in params.items():
                delta = weight * magnitude
                deltas[param] = deltas.get(param, 0) + delta

    # Check keywords (direction comes from prefix)
    if not deltas:
        for keyword, params in _KEYWORDS.items():
            if keyword in t:
                for param, weight in params.items():
                    delta = weight * direction * magnitude
                    deltas[param] = deltas.get(param, 0) + delta

    # Fuzzy fallback — typo tolerance on the last token of the input
    if not deltas:
        tokens = t.split()
        if tokens:
            fuzzy = suggest_keyword(tokens[-1])
            if fuzzy:
                if fuzzy in _COMPARATIVES:
                    for param, weight in _COMPARATIVES[fuzzy].items():
                        deltas[param] = deltas.get(param, 0) + weight * magnitude
                elif fuzzy in _KEYWORDS:
                    for param, weight in _KEYWORDS[fuzzy].items():
                        deltas[param] = deltas.get(param, 0) + weight * direction * magnitude

    return deltas
