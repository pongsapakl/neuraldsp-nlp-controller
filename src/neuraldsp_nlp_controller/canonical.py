"""Canonical tone schema — backend-agnostic representation of a guitar tone.

All values normalized 0-1. Each DSP backend has an adapter that translates
canonical → native parameters.

See docs/decisions/[ACTIVE]_2026-04-04-nlp-on-dsp-architecture-decisions.md,
Decision 3 for design rationale.
"""

from dataclasses import dataclass, field, asdict


@dataclass
class Overdrive:
    active: bool = False
    drive: float = 0.5
    tone: float = 0.5
    level: float = 0.5


@dataclass
class Compressor:
    active: bool = False
    attack: float = 0.5
    release: float = 0.5
    compression: float = 0.5


@dataclass
class Amp:
    character: str = "clean"  # clean, crunch, high_gain, lead
    gain: float = 0.5
    bass: float = 0.5
    mid: float = 0.5
    treble: float = 0.5
    presence: float = 0.5
    master: float = 0.5
    output: float = 0.5


@dataclass
class Chorus:
    active: bool = False
    rate: float = 0.5
    depth: float = 0.5
    mix: float = 0.5


@dataclass
class Delay:
    active: bool = False
    time: float = 0.5
    feedback: float = 0.5
    mix: float = 0.5


@dataclass
class Reverb:
    active: bool = False
    size: float = 0.5
    damping: float = 0.5
    mix: float = 0.5


@dataclass
class CanonicalTone:
    """Full guitar signal chain in canonical form.

    Order: overdrive → compressor → amp → chorus → delay → reverb
    """
    overdrive: Overdrive = field(default_factory=Overdrive)
    compressor: Compressor = field(default_factory=Compressor)
    amp: Amp = field(default_factory=Amp)
    chorus: Chorus = field(default_factory=Chorus)
    delay: Delay = field(default_factory=Delay)
    reverb: Reverb = field(default_factory=Reverb)

    # Source metadata (not part of the tone itself)
    plugin_name: str = ""
    preset_name: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop('plugin_name', None)
        d.pop('preset_name', None)
        return d
