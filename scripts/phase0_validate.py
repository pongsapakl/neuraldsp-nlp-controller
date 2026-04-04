"""
Phase 0 Validation — Neural DSP + pedalboard AudioStream

Tests:
1. Load Neural DSP plugin via pedalboard
2. List available parameters
3. Start AudioStream (guitar in → Neural DSP → audio out)
4. Change parameters while streaming
5. Test multiple buffer sizes (128, 256, 512)

Usage:
  uv run python scripts/phase0_validate.py

Requires: Audio interface connected, Neural DSP plugin installed.
"""

import sys
import time
from pedalboard import Pedalboard, load_plugin
from pedalboard.io import AudioStream


# --- Configuration ---
PLUGINS = {
    "tim_henson": "/Library/Audio/Plug-Ins/VST3/Archetype Tim Henson X.vst3",
    "cory_wong": "/Library/Audio/Plug-Ins/VST3/Archetype Cory Wong X.vst3",
}
BUFFER_SIZES = [128, 256, 512]
SAMPLE_RATE = 44100


def list_audio_devices():
    """Show available audio input/output devices."""
    print("\n=== Audio Devices ===")
    print("\nInput devices:")
    for d in AudioStream.input_device_names:
        print(f"  - {d}")
    print("\nOutput devices:")
    for d in AudioStream.output_device_names:
        print(f"  - {d}")
    print()


def load_and_inspect_plugin(plugin_path: str):
    """Load a Neural DSP plugin and print its parameters."""
    print(f"\n=== Loading: {plugin_path} ===")
    t0 = time.time()
    plugin = load_plugin(plugin_path)
    load_time = time.time() - t0
    print(f"Loaded in {load_time:.2f}s")

    params = plugin.parameters
    print(f"Parameters: {len(params)} total")
    print("\nFirst 30 parameters (name: value [min..max]):")
    for i, (name, param) in enumerate(params.items()):
        if i >= 30:
            print(f"  ... and {len(params) - 30} more")
            break
        try:
            val = getattr(plugin, name)
            print(f"  {name}: {val} [{param.min_value}..{param.max_value}]")
        except Exception as e:
            print(f"  {name}: <error: {e}>")

    return plugin


def test_audiostream(plugin, input_device: str, output_device: str, buffer_size: int):
    """Test AudioStream with given buffer size. Returns True if successful."""
    latency_ms = (buffer_size / SAMPLE_RATE) * 1000
    print(f"\n--- Buffer {buffer_size} (~{latency_ms:.1f}ms) ---")

    try:
        board = Pedalboard([plugin])
        with AudioStream(
            input_device_name=input_device,
            output_device_name=output_device,
            sample_rate=float(SAMPLE_RATE),
            buffer_size=buffer_size,
            plugins=board,
            allow_feedback=True,
        ) as stream:
            print(f"  Stream started. Play guitar for 5 seconds...")
            time.sleep(5)
            print(f"  ✓ No crash, no exception after 5s")
            return True
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        return False


def test_param_change_while_streaming(plugin, input_device: str, output_device: str, plugin_key: str):
    """Test changing parameters while AudioStream is running."""
    print(f"\n=== Parameter Change While Streaming ({plugin_key}) ===")

    # Pick a safe parameter to toggle based on plugin
    test_params = {
        "tim_henson": [
            ("cherubs_amp_gain", [30, 50, 70, 50]),
            ("reverb_mix", [20, 50, 80, 20]),
        ],
        "cory_wong": [
            ("the_amp_snob_gain", [30, 50, 70, 50]),
            ("the_wash_mix", [20, 50, 80, 20]),
        ],
    }

    params_to_test = test_params.get(plugin_key, [])
    if not params_to_test:
        print("  No test parameters defined for this plugin, skipping.")
        return

    try:
        board = Pedalboard([plugin])
        with AudioStream(
            input_device_name=input_device,
            output_device_name=output_device,
            sample_rate=float(SAMPLE_RATE),
            buffer_size=256,
            plugins=board,
            allow_feedback=True,
        ) as stream:
            print("  Stream running. Changing parameters every 2 seconds...")
            print("  Play guitar and listen for tone changes.\n")

            for param_name, values in params_to_test:
                print(f"  Testing: {param_name}")
                for val in values:
                    try:
                        setattr(plugin, param_name, val)
                        actual = getattr(plugin, param_name)
                        print(f"    set {val} → read back {actual}")
                        time.sleep(2)
                    except Exception as e:
                        print(f"    ✗ Error setting {param_name}={val}: {e}")

            print("\n  ✓ Parameter changes completed without crash")
    except Exception as e:
        print(f"  ✗ FAILED: {e}")


def main():
    # Step 1: List devices
    list_audio_devices()

    # Step 2: Let user pick devices (or use defaults)
    input_devices = AudioStream.input_device_names
    output_devices = AudioStream.output_device_names

    if not input_devices or not output_devices:
        print("ERROR: No audio devices found. Connect an audio interface and retry.")
        sys.exit(1)

    print("Select INPUT device:")
    for i, d in enumerate(input_devices):
        print(f"  [{i}] {d}")
    inp_idx = input("Enter number (default 0): ").strip()
    inp_idx = int(inp_idx) if inp_idx else 0
    input_device = input_devices[inp_idx]

    print("\nSelect OUTPUT device:")
    for i, d in enumerate(output_devices):
        print(f"  [{i}] {d}")
    out_idx = input("Enter number (default 0): ").strip()
    out_idx = int(out_idx) if out_idx else 0
    output_device = output_devices[out_idx]

    print(f"\nUsing: {input_device} → {output_device}")

    # Step 3: Choose plugin
    print("\nSelect plugin:")
    plugin_keys = list(PLUGINS.keys())
    for i, k in enumerate(plugin_keys):
        print(f"  [{i}] {k}")
    plugin_idx = input("Enter number (default 0): ").strip()
    plugin_idx = int(plugin_idx) if plugin_idx else 0
    plugin_key = plugin_keys[plugin_idx]
    plugin_path = PLUGINS[plugin_key]

    # Step 4: Load plugin
    plugin = load_and_inspect_plugin(plugin_path)

    # Step 5: Test each buffer size
    print("\n=== AudioStream Latency Test ===")
    results = {}
    for bs in BUFFER_SIZES:
        ok = test_audiostream(plugin, input_device, output_device, bs)
        results[bs] = ok

    # Step 6: Test parameter changes while streaming
    test_param_change_while_streaming(plugin, input_device, output_device, plugin_key)

    # Step 7: Summary
    print("\n" + "=" * 50)
    print("PHASE 0 VALIDATION SUMMARY")
    print("=" * 50)
    print(f"Plugin: {plugin_key} ({plugin_path})")
    print(f"Devices: {input_device} → {output_device}")
    print()
    for bs, ok in results.items():
        latency_ms = (bs / SAMPLE_RATE) * 1000
        status = "✓ PASS" if ok else "✗ FAIL"
        print(f"  Buffer {bs} ({latency_ms:.1f}ms): {status}")
    print()

    all_pass = all(results.values())
    if all_pass:
        print("RESULT: ✓ PHASE 0 PASSED — Real-time AudioStream works.")
        print("Next: Phase 1.1 — Parse Neural DSP factory presets into anchor database.")
    else:
        print("RESULT: ✗ PHASE 0 FAILED — Some buffer sizes had issues.")
        print("Check failures above. Consider file-based fallback if all sizes fail.")


if __name__ == "__main__":
    main()
