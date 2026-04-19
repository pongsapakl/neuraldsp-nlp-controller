"""Neural DSP NLP Controller — Real-time standalone app.

Type a tone description, hear it through your guitar in real-time.

Usage:
  uv run python app.py

Requires: Audio interface connected, at least one Neural DSP Archetype plugin installed.
"""

import os
import queue
import sys
import threading
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from pedalboard import Pedalboard, load_plugin
from pedalboard.io import AudioStream

from neuraldsp_nlp_controller.nlp_engine import NLPEngine
from neuraldsp_nlp_controller.preset_loader import discover_mapping, list_factory_presets

# ── Configuration ────────────────────────────────────────────────────

ANCHOR_PATH = Path(__file__).parent / "data" / "anchors.yaml"
SAMPLE_RATE = 44100
BUFFER_SIZE = 256

AVAILABLE_PLUGINS = {
    "Archetype Tim Henson X": "/Library/Audio/Plug-Ins/VST3/Archetype Tim Henson X.vst3",
    "Archetype Cory Wong X": "/Library/Audio/Plug-Ins/VST3/Archetype Cory Wong X.vst3",
}

PRESET_DIRS = {
    "Archetype Tim Henson X": "/Library/Audio/Presets/Neural DSP/Archetype Tim Henson X",
    "Archetype Cory Wong X": "/Library/Audio/Presets/Neural DSP/Archetype Cory Wong X",
}

HOST = "127.0.0.1"
PORT = 7860


# ── Plugin Loader (main-thread service) ─────────────────────────────

_load_queue: queue.Queue = queue.Queue()


def _load_plugin_on_main_thread(plugin_name: str):
    """Load a fresh plugin instance, routing to the main thread if needed.

    VST3 plugins must be created on the main thread (macOS/Cocoa requirement).
    Worker threads (FastAPI handlers) post requests here and wait.
    """
    path = AVAILABLE_PLUGINS[plugin_name]
    if threading.current_thread() is threading.main_thread():
        return load_plugin(path)

    result: dict = {}
    event = threading.Event()
    _load_queue.put((plugin_name, path, event, result))
    if not event.wait(timeout=30):
        raise RuntimeError(f"Timeout loading {plugin_name}")
    if "error" in result:
        raise RuntimeError(result["error"])
    return result["plugin"]


def _main_thread_loader_loop():
    """Run on the main thread after the server starts. Processes load requests."""
    try:
        while True:
            try:
                _, path, event, result = _load_queue.get(timeout=0.5)
                try:
                    result["plugin"] = load_plugin(path)
                except Exception as e:
                    result["error"] = str(e)
                event.set()
            except queue.Empty:
                continue
    except KeyboardInterrupt:
        pass


# ── App State ────────────────────────────────────────────────────────

class AppState:
    def __init__(self):
        self.plugin = None
        self.plugin_name = ""
        self.stream = None
        self.board = None
        self.engine = None
        self.key_map: dict[str, str] | None = None
        self.current_tone = None
        self.last_results: list[dict] = []
        self.tone_loaded = False
        self.input_device = ""
        self.output_device = ""


state = AppState()


# ── Core Functions ───────────────────────────────────────────────────

def get_installed_plugins() -> list[str]:
    return [name for name, path in AVAILABLE_PLUGINS.items()
            if Path(path).exists()]


def get_audio_devices() -> tuple[list[str], list[str]]:
    return list(AudioStream.input_device_names), list(AudioStream.output_device_names)


def _start_stream(plugin_name: str, input_device: str, output_device: str) -> str:
    """Load a fresh plugin instance and start AudioStream."""
    _stop_stream()

    try:
        plugin = _load_plugin_on_main_thread(plugin_name)
    except RuntimeError as e:
        return f"Failed to load {plugin_name}: {e}"

    try:
        preset_dir = PRESET_DIRS.get(plugin_name, "")
        presets = list_factory_presets(preset_dir) if preset_dir else []
        state.key_map = discover_mapping(plugin, presets[0]) if presets else None

        state.plugin = plugin
        state.plugin_name = plugin_name
        state.input_device = input_device
        state.output_device = output_device
        state.board = Pedalboard([state.plugin])
        state.stream = AudioStream(
            input_device_name=input_device,
            output_device_name=output_device,
            sample_rate=float(SAMPLE_RATE),
            buffer_size=BUFFER_SIZE,
            plugins=state.board,
            allow_feedback=True,
        )
        state.stream.__enter__()
        return f"Streaming: {input_device} -> {plugin_name} -> {output_device}"
    except Exception as e:
        state.stream = None
        state.plugin = None
        return f"Failed to start: {e}"


def _stop_stream():
    if state.stream is not None:
        try:
            state.stream.__exit__(None, None, None)
        except Exception:
            pass
    state.stream = None
    state.plugin = None
    state.board = None
    state.key_map = None
    state.current_tone = None
    state.last_results = []
    state.tone_loaded = False


def switch_plugin(plugin_name: str, input_device: str, output_device: str) -> str:
    return _start_stream(plugin_name, input_device, output_device)


# ── Main ─────────────────────────────────────────────────────────────

def _run_server():
    import uvicorn
    from server import build_app
    uvicorn.run(build_app(), host=HOST, port=PORT, log_level="info",
                access_log=False)


if __name__ == "__main__":
    # Make `import app` in server.py resolve to this __main__ module, so the
    # AppState singleton and state are shared (otherwise Python reimports app.py
    # as a distinct module with its own empty state).
    sys.modules["app"] = sys.modules[__name__]

    installed = get_installed_plugins()
    if not installed:
        print("ERROR: No Neural DSP plugins found.")
        sys.exit(1)

    inputs, outputs = get_audio_devices()
    if not inputs or not outputs:
        print("ERROR: No audio devices found. Connect an audio interface.")
        sys.exit(1)

    if not ANCHOR_PATH.exists():
        print(f"ERROR: Anchor database not found at {ANCHOR_PATH}")
        print()
        print("First-time setup: build the anchor database from your Neural DSP presets:")
        print("  uv run python scripts/build_anchor_db.py")
        print()
        print("This reads your installed Neural DSP factory presets and extracts")
        print("semantic descriptions for NLP matching. Takes ~10 minutes, runs once.")
        sys.exit(1)

    print("Loading NLP engine...")
    state.engine = NLPEngine(ANCHOR_PATH)
    print(f"  {len(state.engine.anchors)} anchors loaded.")

    plugin_name = installed[0]
    input_device = inputs[0]
    output_device = outputs[0]
    print(f"Starting audio: {input_device} -> {plugin_name} -> {output_device}")
    print(f"  {_start_stream(plugin_name, input_device, output_device)}")

    server_thread = threading.Thread(target=_run_server, daemon=True, name="uvicorn")
    server_thread.start()
    print(f"Server: http://{HOST}:{PORT}")
    print("Main thread ready for plugin load requests.")
    _main_thread_loader_loop()
