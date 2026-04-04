"""
Neural DSP preset loader — auto-discovered parameter mapping.

Parses factory preset files (proprietary binary) and applies them to
pedalboard-loaded Neural DSP plugins using the pedalboard parameter API.

No per-plugin config needed. The mapping is auto-discovered by:
1. Grouping preset keys and pedalboard params by prefix
2. Matching groups by overlapping suffixes (Bass↔bass, Treble↔treble, etc.)
3. Handling derived patterns (EQ sub-prefixes, cab L/R, room L/R, mic types)
4. Resolving values with auto-scaling and enum matching

See docs/research/2026-04-05-preset-loading-spike-results.md for full details.
"""

import re
from pathlib import Path


# ── Preset binary parser ──────────────────────────────────────────────

def parse_preset(path: str | Path) -> dict[str, str]:
    """Parse Neural DSP binary preset file into {key: value_string} dict.

    The factory preset format is proprietary binary with null-separated
    key-value pairs. Keys are camelCase identifiers, values are numbers
    or booleans stored as ASCII strings.
    """
    with open(path, 'rb') as f:
        raw = f.read()

    # Extract runs of printable ASCII
    runs: list[tuple[int, str]] = []
    current: list[str] = []
    start = 0
    for i, b in enumerate(raw):
        if 32 <= b < 127:
            if not current:
                start = i
            current.append(chr(b))
        else:
            if current:
                runs.append((start, ''.join(current)))
                current = []
    if current:
        runs.append((start, ''.join(current)))

    # Adjacent runs where key is identifier, value is number/bool
    kv: dict[str, str] = {}
    for i in range(len(runs) - 1):
        _, key = runs[i]
        _, val = runs[i + 1]
        if re.match(r'^[a-zA-Z][a-zA-Z0-9]+$', key):
            if re.match(r'^-?\d+\.?\d*$|^true$|^false$', val):
                kv[key] = val
    return kv


def list_factory_presets(preset_dir: str | Path) -> list[Path]:
    """List all factory preset files (.xml) under a preset directory."""
    d = Path(preset_dir)
    if not d.exists():
        return []
    return sorted(d.rglob("*.xml"))


# ── Name conversion ───────────────────────────────────────────────────

def camel_to_snake(name: str) -> str:
    """Convert camelCase to snake_case with number separation.

    Examples: acousticBass → acoustic_bass, EQBand7 → eq_band_7
    """
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name)
    s = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', s)
    s = s.lower()
    s = re.sub(r'([a-z])(\d)', r'\1_\2', s)
    return s


# ── Value resolution ──────────────────────────────────────────────────

def _resolve_enum(preset_val: str, valid_values: list[str], pb_name: str) -> str | None:
    """Resolve preset value (int/bool string) to pedalboard enum string."""
    # Bool → 2-value enum (e.g., compAttack: true → "Fast")
    if preset_val in ('true', 'false'):
        if len(valid_values) == 2:
            return valid_values[1 if preset_val == 'true' else 0]
        return None

    try:
        num = float(preset_val)
    except ValueError:
        return None

    # Check if enum values contain units (L/R/cents/Hz) — match by value not index
    sample = valid_values[0] if valid_values else ""
    has_units = bool(re.search(r'\d+\s*(L|R|cents|st|Hz|kHz|BPM)', sample))

    # Direct index for non-unit enums
    if not has_units and num == int(num) and 0 <= int(num) < len(valid_values):
        return valid_values[int(num)]

    # Numeric matching for value-based enums
    best, best_dist = None, float('inf')

    def try_match(target):
        nonlocal best, best_dist
        for vv in valid_values:
            if vv in ('C', 'OFF'):
                ev = 0.0
            else:
                m = re.match(r'^(-?\d+\.?\d*)\s*', vv)
                if not m:
                    continue
                ev = float(m.group(1))
                if ' L' in vv:
                    ev = -ev
            d = abs(ev - target)
            if d < best_dist:
                best_dist = d
                best = vv

    try_match(num)
    if 'pan' in pb_name and best_dist > 2:
        try_match(num * 50)  # preset -1..1 → pedalboard -50..50

    if best is not None and best_dist < 2:
        return best

    # HPF/LPF: extreme values → OFF
    if ('hpf' in pb_name or 'lpf' in pb_name) and 'OFF' in valid_values:
        if num <= 20 or num >= 20000:
            return 'OFF'

    return None


def resolve_value(preset_val: str, pb_name: str, plugin) -> object:
    """Convert preset value string to correct pedalboard value type."""
    param = plugin.parameters[pb_name]

    # Boolean param
    if param.min_value is False and param.max_value is True:
        if preset_val in ('true', 'false'):
            return preset_val == 'true'
        try:
            return bool(int(float(preset_val)))
        except ValueError:
            return None

    # String enum param
    if param.min_value is None and param.max_value is None:
        try:
            valid = list(param.valid_values)
        except (AttributeError, TypeError):
            return None
        return _resolve_enum(preset_val, valid, pb_name)

    # Numeric param
    try:
        val = float(preset_val)
    except ValueError:
        return None

    min_v, max_v = float(param.min_value), float(param.max_value)

    # Auto-detect 0-1 → 0-100 scaling
    if max_v == 100.0 and min_v == 0.0 and 0 <= val <= 1.0001:
        val *= 100.0

    return max(min_v, min(max_v, val))


# ── Auto-discovery engine ─────────────────────────────────────────────

# Known suffixes for splitting camelCase preset keys into (prefix, suffix)
_KNOWN_SUFFIXES = {
    'bass', 'treble', 'middle', 'mid', 'gain', 'drive', 'level', 'output',
    'presence', 'volume', 'master', 'blend', 'tone', 'mix', 'active',
    'attack', 'decay', 'release', 'feedback', 'time', 'rate', 'width',
    'compression', 'bright', 'shimmer', 'spread',
}

# Internal/UI-only preset keys — never affect audio
_KNOWN_SKIP_KEYS = {
    'sectionActive', 'sectionActiveInternal', 'cabStereo',
    'leftCabStereo', 'rightCabStereo',
    'multivoicerVoicingID', 'multivoicerScreenMode',
}

# Well-known preset key → pedalboard param renames
_WELL_KNOWN_MAP = {
    'selectedAmp': 'amp_type',
    'selectedCab': 'cab_type_unlinked',
    'ampCabLinkedState': 'amp_cab_linked',
    'multivoicerUnison': 'multivoicer_unisons',
}

# EQ band frequency names (standard 9-band for Neural DSP)
_EQ_FREQ_NAMES = [
    '65_hz', '125_hz', '250_hz', '500_hz', '1_khz',
    '2_khz', '4_khz', '8_khz', '16_khz',
]


def _split_camel_prefix(key: str) -> tuple[str, str]:
    """Split a camelCase preset key into (prefix, suffix)."""
    key_lower = key.lower()
    for suffix in sorted(_KNOWN_SUFFIXES, key=len, reverse=True):
        if key_lower.endswith(suffix) and len(key) > len(suffix):
            prefix = key[:len(key) - len(suffix)]
            actual_suffix = key[len(key) - len(suffix):]
            if prefix[-1].islower() and actual_suffix[0].isupper():
                return prefix, actual_suffix

    m = re.match(r'^([a-z]+[a-z0-9]*)((?:[A-Z]|EQ).+)$', key)
    if m:
        return m.group(1), m.group(2)

    return key, ''


def _split_snake_prefix(name: str, all_names: set[str]) -> tuple[str, str]:
    """Split a snake_case pedalboard param into (prefix, suffix)."""
    parts = name.split('_')
    for i in range(len(parts) - 1, 0, -1):
        prefix = '_'.join(parts[:i])
        suffix = '_'.join(parts[i:])
        count = sum(1 for n in all_names if n.startswith(prefix + '_') and n != name)
        if count >= 2:
            return prefix, suffix
    return name, ''


def _normalize_suffix(s: str) -> str:
    """Normalize a suffix for cross-system comparison."""
    s = camel_to_snake(s).lower().strip('_')
    s = s.replace('output_level', 'output')
    return s


def discover_mapping(plugin, preset_path: str | Path) -> dict[str, str]:
    """Auto-discover the mapping from preset keys to pedalboard param names.

    Returns {preset_key: pedalboard_param_name} for all mappable keys.

    Algorithm:
    1. Group both sides by prefix, match by overlapping suffixes
    2. Handle EQ sub-prefixes (numbered bands + frequency-named bands)
    3. Handle cab/room L/R patterns
    4. Handle per-amp mic type slots
    5. Apply well-known renames and direct snake_case conversion
    """
    preset_params = parse_preset(str(preset_path))
    pb_param_names = set(plugin.parameters.keys())

    # Step 1: Group preset keys by prefix
    preset_groups: dict[str, dict[str, str]] = {}
    for key in preset_params:
        prefix, suffix = _split_camel_prefix(key)
        if suffix:
            preset_groups.setdefault(prefix, {})[suffix] = key
        else:
            preset_groups[key] = {}

    # Step 2: Group pedalboard params by prefix
    pb_groups: dict[str, dict[str, str]] = {}
    for name in pb_param_names:
        prefix, suffix = _split_snake_prefix(name, pb_param_names)
        if suffix:
            pb_groups.setdefault(prefix, {})[suffix] = name
        else:
            pb_groups[name] = {}

    # Step 3: Match preset prefix groups to pedalboard prefix groups
    prefix_map: dict[str, str] = {}
    key_map: dict[str, str] = {}
    amp_prefixes: list[tuple[str, str]] = []

    for p_prefix, p_suffixes in preset_groups.items():
        if not p_suffixes:
            continue

        p_norm = {_normalize_suffix(s): orig for s, orig in p_suffixes.items()}
        best_match, best_score, best_details = None, 0, {}

        for pb_prefix, pb_suffixes in pb_groups.items():
            if not pb_suffixes:
                continue
            matches = {}
            for p_suf_norm, p_orig in p_norm.items():
                for pb_suf, pb_orig in pb_suffixes.items():
                    pb_suf_norm = _normalize_suffix(pb_suf)
                    if (p_suf_norm == pb_suf_norm
                            or (p_suf_norm == 'mid' and pb_suf_norm == 'middle')
                            or (p_suf_norm == 'output_level' and pb_suf_norm == 'output')):
                        matches[p_orig] = pb_orig
            if len(matches) > best_score:
                best_score = len(matches)
                best_match = pb_prefix
                best_details = matches

        if best_match and best_score >= 2:
            prefix_map[p_prefix] = best_match
            for preset_key, pb_name in best_details.items():
                key_map[preset_key] = pb_name
            # Track amp prefixes (have bass/treble/gain)
            if any(s.lower() in ('bass', 'treble', 'gain') for s in best_details):
                amp_prefixes.append((p_prefix, best_match))

    # Step 4: Pattern handlers for remaining unmapped keys
    for key in preset_params:
        if key in key_map or key in _KNOWN_SKIP_KEYS:
            continue

        # Pattern A: EQ sub-prefix
        eq_match = re.match(r'^(\w+?)EQ(.+)$', key)
        if eq_match:
            eq_base, eq_suffix = eq_match.group(1), eq_match.group(2)
            if eq_base in prefix_map:
                pb_amp = prefix_map[eq_base]
                if '_amp_' in pb_amp:
                    eq_prefix = pb_amp + '_eq'
                elif pb_amp.endswith('_amp'):
                    eq_prefix = pb_amp[:-4] + '_eq'
                else:
                    eq_prefix = pb_amp + '_eq'

                # Band numbers → try band_N, then frequency names
                band_match = re.match(r'^Band(\d+)$', eq_suffix)
                if band_match:
                    band_num = int(band_match.group(1))
                    candidate = f"{eq_prefix}_band_{band_num}"
                    if candidate in pb_param_names:
                        key_map[key] = candidate
                        continue
                    if 1 <= band_num <= len(_EQ_FREQ_NAMES):
                        candidate = f"{eq_prefix}_{_EQ_FREQ_NAMES[band_num - 1]}"
                        if candidate in pb_param_names:
                            key_map[key] = candidate
                            continue

                # Hpf/Lpf
                if eq_suffix in ('Hpf', 'Lpf'):
                    for try_suf in [eq_suffix.lower(), 'high_pass' if eq_suffix == 'Hpf' else 'low_pass']:
                        candidate = f"{eq_prefix}_{try_suf}"
                        if candidate in pb_param_names:
                            key_map[key] = candidate
                            break
                    if key in key_map:
                        continue

                # Other EQ suffixes (Active, etc.)
                candidate = f"{eq_prefix}_{camel_to_snake(eq_suffix)}"
                if candidate in pb_param_names:
                    key_map[key] = candidate
                    continue

        # Pattern B: Cab L/R params
        cab_match = re.match(r'^(left|right)Cab(\d*)((?:[A-Z].*)?)$', key)
        if cab_match:
            side = 'l' if cab_match.group(1) == 'left' else 'r'
            slot, suffix = cab_match.group(2), cab_match.group(3)

            if slot and suffix == 'MicType':
                slot_idx = int(slot)
                if slot_idx < len(amp_prefixes):
                    _, pb_amp = amp_prefixes[slot_idx]
                    candidate = f"{pb_amp}_cab_mic_{side}_type"
                    if candidate in pb_param_names:
                        key_map[key] = candidate
                        continue
                # Fallback: search all mic type params
                mic_params = sorted(n for n in pb_param_names if n.endswith(f'_cab_mic_{side}_type'))
                if slot_idx < len(mic_params):
                    key_map[key] = mic_params[slot_idx]
                    continue
            elif not slot and suffix:
                snake_suf = camel_to_snake(suffix)
                if snake_suf == 'mic_level':
                    snake_suf = 'level'
                candidate = f"cab_{side}_{snake_suf}"
                if candidate in pb_param_names:
                    key_map[key] = candidate
                    continue

        # Pattern C: Room L/R params
        room_match = re.match(r'^(left|right)Room(.+)$', key)
        if room_match:
            side = 'l' if room_match.group(1) == 'left' else 'r'
            snake_suf = camel_to_snake(room_match.group(2))
            if snake_suf == 'mic_level':
                snake_suf = 'send'
            candidate = f"room_{side}_{snake_suf}"
            if candidate in pb_param_names:
                key_map[key] = candidate
                continue

        # Pattern D: Prefix-based suffix mapping (Mid→middle, OutputLevel→output, etc.)
        for p_prefix, pb_prefix in prefix_map.items():
            if key.startswith(p_prefix) and len(key) > len(p_prefix):
                suffix = key[len(p_prefix):]
                renames = {'Mid': 'middle', 'OutputLevel': 'output'}
                candidate = f"{pb_prefix}_{renames.get(suffix, camel_to_snake(suffix))}"
                if candidate in pb_param_names:
                    key_map[key] = candidate
                    break

        if key in key_map:
            continue

        # Pattern E: Well-known keys
        if key in _WELL_KNOWN_MAP and _WELL_KNOWN_MAP[key] in pb_param_names:
            key_map[key] = _WELL_KNOWN_MAP[key]
            continue

        # Pattern F: Direct snake_case conversion
        snake = camel_to_snake(key)
        if snake in pb_param_names:
            key_map[key] = snake
            continue
        snake2 = re.sub(r'(\d+)', r'_\1_', snake).replace('__', '_').strip('_')
        if snake2 in pb_param_names:
            key_map[key] = snake2
            continue

    return key_map


# ── Public API ────────────────────────────────────────────────────────

def load_preset(plugin, preset_path: str | Path, key_map: dict[str, str]) -> dict:
    """Apply a Neural DSP factory preset to a pedalboard plugin.

    Args:
        plugin: A pedalboard-loaded VST3Plugin instance.
        preset_path: Path to a Neural DSP factory preset file.
        key_map: Mapping from preset keys to pedalboard param names,
                 as returned by discover_mapping().

    Returns:
        Dict with keys: applied (int), failed (int), skipped (int), errors (list[str]).
    """
    preset_params = parse_preset(str(preset_path))
    applied, failed, skipped = 0, 0, 0
    errors: list[str] = []

    for pk, pv in preset_params.items():
        pb_name = key_map.get(pk)
        if pb_name is None:
            skipped += 1
            continue

        resolved = resolve_value(pv, pb_name, plugin)
        if resolved is None:
            failed += 1
            errors.append(f'{pk}={pv} → {pb_name}: unresolved value')
            continue

        try:
            setattr(plugin, pb_name, resolved)
            applied += 1
        except Exception as e:
            failed += 1
            errors.append(f'{pk}={pv} → {pb_name}: {e}')

    return {'applied': applied, 'failed': failed, 'skipped': skipped, 'errors': errors}


def get_preset_name(preset_path: str | Path) -> str:
    """Extract the human-readable name from a preset file path."""
    return Path(preset_path).stem
