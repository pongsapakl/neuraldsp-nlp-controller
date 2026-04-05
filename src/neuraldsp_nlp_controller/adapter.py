"""Neural DSP adapter — translates between canonical tone schema and plugin params.

Two directions:
  extract(plugin) → CanonicalTone   (read plugin state into canonical form)
  apply(plugin, tone)               (set plugin params from canonical tone)
"""

from .canonical import CanonicalTone, Amp, Overdrive, Compressor, Chorus, Delay, Reverb


# ── Per-plugin configuration ─────────────────────────────────────────

# Maps amp_type enum value → (canonical character, pedalboard prefix)
_AMP_CHANNELS = {
    "Archetype Tim Henson X": {
        "Roses":   ("clean",     "roses_amp"),
        "Cherubs": ("crunch",    "cherubs_amp"),
        "Pink":    ("lead",      "pink_amp"),
    },
    "Archetype Cory Wong X": {
        "Funk":  ("clean",  "d_i_funk_console"),
        "Clean": ("clean",  "the_clean_machine"),
        "Snob":  ("crunch", "the_amp_snob"),
    },
}

# Maps canonical effect fields → pedalboard param names per plugin
# Format: {canonical_field: pedalboard_param_name}
_EFFECTS = {
    "Archetype Tim Henson X": {
        "overdrive": {
            "active": "overdrive_active",
            "drive":  "overdrive_drive",
            "tone":   "overdrive_tone",
            "level":  "overdrive_level",
        },
        "compressor": {
            "active":      "compressor_active",
            "compression": "compressor_compression",
            "level":       "compressor_level",
            # attack is enum (Slow/Fast), map separately
        },
        "chorus": {
            "active": "chorus_active",
            "mix":    "chorus_mix",
            # rate/depth not exposed on Tim Henson
        },
        "delay": {
            "active":   "delay_active",
            "time":     "delay_time",
            "feedback": "delay_feedback",
            "mix":      "delay_mix",
        },
        "reverb": {
            "active":  "reverb_active",
            "size":    "reverb_decay",
            "damping": "reverb_high_cut",
            "mix":     "reverb_mix",
        },
    },
    "Archetype Cory Wong X": {
        "overdrive": {
            "active": "the_tuber_active",
            "drive":  "the_tuber_drive",
            "tone":   "the_tuber_tone",
            "level":  "the_tuber_level",
        },
        "compressor": {
            "active":      "the_4th_position_comp_active",
            "compression": "the_4th_position_comp_compression",
            "level":       "the_4th_position_comp_volume",
        },
        "chorus": {
            "active": "the_80s_chorus_active",
            "rate":   "the_80s_chorus_rate",
            "depth":  "the_80s_chorus_width",
            "mix":    "the_80s_chorus_mix",
        },
        "delay": {
            "active":   "delay_y_y_active",
            "time":     "delay_y_y_time_l",
            "feedback": "delay_y_y_feedback",
            "mix":      "delay_y_y_mix",
        },
        "reverb": {
            "active":  "the_wash_active",
            "size":    "the_wash_decay",
            "damping": "the_wash_high_cut",
            "mix":     "the_wash_mix",
        },
    },
}

# Amp params that exist across all channels (suffix after prefix)
_AMP_PARAMS = {
    "gain":     ("gain", "volume", "tube_sat"),  # aliases per plugin
    "bass":     ("bass",),
    "mid":      ("middle", "mids"),
    "treble":   ("treble", "highs"),
    "presence": ("presence",),
    "master":   ("master",),
    "output":   ("output",),
}


def _detect_plugin_name(plugin) -> str:
    """Detect which Neural DSP plugin this is."""
    params = set(plugin.parameters.keys())
    if "roses_amp_gain" in params:
        return "Archetype Tim Henson X"
    if "the_amp_snob_bass" in params:
        return "Archetype Cory Wong X"
    raise ValueError(f"Unknown plugin — params don't match any known Neural DSP plugin")


def _read_param(plugin, name: str) -> float | bool | str | None:
    """Read a pedalboard param value, return None if missing."""
    if name not in plugin.parameters:
        return None
    return getattr(plugin, name)


def _normalize(value: float, min_v: float, max_v: float) -> float:
    """Normalize a value to 0-1 range."""
    if max_v == min_v:
        return 0.0
    return max(0.0, min((value - min_v) / (max_v - min_v), 1.0))


def _denormalize(value: float, min_v: float, max_v: float) -> float:
    """Convert 0-1 value back to native range."""
    return min_v + value * (max_v - min_v)


def _get_param_range(plugin, name: str) -> tuple[float, float]:
    """Get min/max range of a numeric param."""
    p = plugin.parameters[name]
    return float(p.min_value), float(p.max_value)


# ── Extract: plugin state → canonical ────────────────────────────────

def extract(plugin) -> CanonicalTone:
    """Read current plugin state and return a CanonicalTone."""
    plugin_name = _detect_plugin_name(plugin)
    channels = _AMP_CHANNELS[plugin_name]
    effects = _EFFECTS[plugin_name]
    params = set(plugin.parameters.keys())

    # Amp channel
    amp_type_val = _read_param(plugin, "amp_type")
    if amp_type_val and amp_type_val in channels:
        character, prefix = channels[amp_type_val]
    else:
        # Default to first channel
        first_key = next(iter(channels))
        character, prefix = channels[first_key]

    # Read amp params
    def read_amp(canonical_name: str) -> float:
        for suffix in _AMP_PARAMS.get(canonical_name, (canonical_name,)):
            full = f"{prefix}_{suffix}"
            if full in params:
                val = _read_param(plugin, full)
                if val is not None:
                    mn, mx = _get_param_range(plugin, full)
                    return _normalize(float(val), mn, mx)
        return 0.5  # default

    amp = Amp(
        character=character,
        gain=read_amp("gain"),
        bass=read_amp("bass"),
        mid=read_amp("mid"),
        treble=read_amp("treble"),
        presence=read_amp("presence"),
        master=read_amp("master"),
        output=read_amp("output"),
    )

    # Read effects
    def read_effect(section: str, field: str) -> float | bool:
        pb_name = effects.get(section, {}).get(field)
        if not pb_name or pb_name not in params:
            return False if field == "active" else 0.5
        val = _read_param(plugin, pb_name)
        if val is None:
            return False if field == "active" else 0.5
        if isinstance(val, bool) or field == "active":
            return bool(val)
        mn, mx = _get_param_range(plugin, pb_name)
        return _normalize(float(val), mn, mx)

    overdrive = Overdrive(
        active=read_effect("overdrive", "active"),
        drive=read_effect("overdrive", "drive"),
        tone=read_effect("overdrive", "tone"),
        level=read_effect("overdrive", "level"),
    )

    compressor = Compressor(
        active=read_effect("compressor", "active"),
        compression=read_effect("compressor", "compression"),
    )

    chorus = Chorus(
        active=read_effect("chorus", "active"),
        rate=read_effect("chorus", "rate"),
        depth=read_effect("chorus", "depth"),
        mix=read_effect("chorus", "mix"),
    )

    delay = Delay(
        active=read_effect("delay", "active"),
        time=read_effect("delay", "time"),
        feedback=read_effect("delay", "feedback"),
        mix=read_effect("delay", "mix"),
    )

    reverb = Reverb(
        active=read_effect("reverb", "active"),
        size=read_effect("reverb", "size"),
        damping=read_effect("reverb", "damping"),
        mix=read_effect("reverb", "mix"),
    )

    return CanonicalTone(
        amp=amp,
        overdrive=overdrive,
        compressor=compressor,
        chorus=chorus,
        delay=delay,
        reverb=reverb,
        plugin_name=plugin_name,
    )


# ── Apply: canonical → plugin state ──────────────────────────────────

def apply(plugin, tone: CanonicalTone) -> dict:
    """Set plugin params from a CanonicalTone. Returns stats."""
    plugin_name = _detect_plugin_name(plugin)
    channels = _AMP_CHANNELS[plugin_name]
    effects = _EFFECTS[plugin_name]
    params = set(plugin.parameters.keys())
    applied, skipped = 0, 0

    # Set amp channel
    for amp_val, (char, _) in channels.items():
        if char == tone.amp.character:
            try:
                setattr(plugin, "amp_type", amp_val)
                applied += 1
            except Exception:
                skipped += 1
            break

    # Get the prefix for the selected channel
    prefix = None
    for amp_val, (char, pfx) in channels.items():
        if char == tone.amp.character:
            prefix = pfx
            break
    if not prefix:
        prefix = next(iter(channels.values()))[1]

    # Set amp params
    def set_amp(canonical_name: str, value: float):
        nonlocal applied, skipped
        for suffix in _AMP_PARAMS.get(canonical_name, (canonical_name,)):
            full = f"{prefix}_{suffix}"
            if full in params:
                mn, mx = _get_param_range(plugin, full)
                try:
                    setattr(plugin, full, _denormalize(value, mn, mx))
                    applied += 1
                except Exception:
                    skipped += 1
                return
        skipped += 1

    set_amp("gain", tone.amp.gain)
    set_amp("bass", tone.amp.bass)
    set_amp("mid", tone.amp.mid)
    set_amp("treble", tone.amp.treble)
    set_amp("presence", tone.amp.presence)
    set_amp("master", tone.amp.master)
    set_amp("output", tone.amp.output)

    # Set effects
    def set_effect(section: str, field: str, value: float | bool):
        nonlocal applied, skipped
        pb_name = effects.get(section, {}).get(field)
        if not pb_name or pb_name not in params:
            skipped += 1
            return
        try:
            if isinstance(value, bool) or field == "active":
                setattr(plugin, pb_name, bool(value))
            else:
                mn, mx = _get_param_range(plugin, pb_name)
                setattr(plugin, pb_name, _denormalize(value, mn, mx))
            applied += 1
        except Exception:
            skipped += 1

    # Overdrive
    set_effect("overdrive", "active", tone.overdrive.active)
    set_effect("overdrive", "drive", tone.overdrive.drive)
    set_effect("overdrive", "tone", tone.overdrive.tone)
    set_effect("overdrive", "level", tone.overdrive.level)

    # Compressor
    set_effect("compressor", "active", tone.compressor.active)
    set_effect("compressor", "compression", tone.compressor.compression)

    # Chorus
    set_effect("chorus", "active", tone.chorus.active)
    set_effect("chorus", "rate", tone.chorus.rate)
    set_effect("chorus", "depth", tone.chorus.depth)
    set_effect("chorus", "mix", tone.chorus.mix)

    # Delay
    set_effect("delay", "active", tone.delay.active)
    set_effect("delay", "time", tone.delay.time)
    set_effect("delay", "feedback", tone.delay.feedback)
    set_effect("delay", "mix", tone.delay.mix)

    # Reverb
    set_effect("reverb", "active", tone.reverb.active)
    set_effect("reverb", "size", tone.reverb.size)
    set_effect("reverb", "damping", tone.reverb.damping)
    set_effect("reverb", "mix", tone.reverb.mix)

    return {"applied": applied, "skipped": skipped}


# ── Delta: adjust specific params relative to current ──────────────

def apply_delta(plugin, deltas: dict[str, float]) -> dict:
    """Apply parameter deltas to current plugin state.

    Each delta is in canonical 0-1 space. Reads current value from plugin,
    adds delta, clamps to valid range, sets new value. Only touches the
    params specified — everything else stays untouched.

    Args:
        plugin: pedalboard plugin instance (already streaming)
        deltas: {canonical_param: delta} e.g. {"amp.treble": -0.1}
                Canonical params: amp.gain, amp.bass, amp.mid, amp.treble,
                amp.presence, amp.master, amp.output, overdrive.drive,
                overdrive.tone, overdrive.level, compressor.compression,
                chorus.rate, chorus.depth, chorus.mix, delay.time,
                delay.feedback, delay.mix, reverb.size, reverb.damping,
                reverb.mix

    Returns:
        Dict with applied (int), skipped (int), changes (list[str]).
    """
    plugin_name = _detect_plugin_name(plugin)
    channels = _AMP_CHANNELS[plugin_name]
    effects = _EFFECTS[plugin_name]
    params = set(plugin.parameters.keys())

    # Detect active amp channel
    amp_type_val = _read_param(plugin, "amp_type")
    prefix = None
    if amp_type_val and amp_type_val in channels:
        _, prefix = channels[amp_type_val]
    if not prefix:
        prefix = next(iter(channels.values()))[1]

    applied, skipped = 0, 0
    changes: list[str] = []

    for canonical_param, delta in deltas.items():
        section, field = canonical_param.split(".", 1)

        # Find the pedalboard param name
        pb_name = None
        if section == "amp":
            for suffix in _AMP_PARAMS.get(field, (field,)):
                full = f"{prefix}_{suffix}"
                if full in params:
                    pb_name = full
                    break
        else:
            pb_name = effects.get(section, {}).get(field)
            if pb_name and pb_name not in params:
                pb_name = None

        if not pb_name:
            skipped += 1
            continue

        # Handle boolean params (active toggles)
        if field == "active":
            current = _read_param(plugin, pb_name)
            new_val = delta > 0  # positive = activate, negative = deactivate
            if current != new_val:
                try:
                    setattr(plugin, pb_name, new_val)
                    applied += 1
                    changes.append(f"{canonical_param}: {'on' if new_val else 'off'}")
                except Exception:
                    skipped += 1
            continue

        # Read current value in 0-1 space
        mn, mx = _get_param_range(plugin, pb_name)
        current_raw = _read_param(plugin, pb_name)
        if current_raw is None:
            skipped += 1
            continue
        current_norm = _normalize(float(current_raw), mn, mx)

        # Apply delta and clamp
        new_norm = max(0.0, min(1.0, current_norm + delta))
        new_raw = _denormalize(new_norm, mn, mx)

        try:
            setattr(plugin, pb_name, new_raw)
            applied += 1
            changes.append(f"{canonical_param}: {current_norm:.2f} → {new_norm:.2f}")
        except Exception:
            skipped += 1

    return {"applied": applied, "skipped": skipped, "changes": changes}
