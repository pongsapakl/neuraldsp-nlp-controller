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

import gradio as gr
from pedalboard import Pedalboard, load_plugin
from pedalboard.io import AudioStream

from neuraldsp_nlp_controller.adapter import apply_delta
from neuraldsp_nlp_controller.nlp_engine import NLPEngine
from neuraldsp_nlp_controller.preset_loader import discover_mapping, load_preset, blend_presets, list_factory_presets
from neuraldsp_nlp_controller.refinement import parse_deltas, recognized_keywords

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


# ── Plugin Loader (main-thread service) ─────────────────────────────

_load_queue: queue.Queue = queue.Queue()


def _load_plugin_on_main_thread(plugin_name: str):
    """Load a fresh plugin instance, routing to the main thread if needed.

    VST3 plugins must be created on the main thread (macOS/Cocoa requirement).
    If called from the main thread (startup), loads directly.
    If called from a worker thread (Gradio callback), sends a request to the
    main-thread loader loop and blocks until it's fulfilled.
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
    """Run on the main thread after Gradio launches. Processes load requests."""
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
        self.tone_loaded = False  # True after a tone is applied; enables refine
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
        # Discover preset key mapping for raw preset loading
        preset_dir = PRESET_DIRS.get(plugin_name, "")
        presets = list_factory_presets(preset_dir) if preset_dir else []
        if presets:
            state.key_map = discover_mapping(plugin, presets[0])
        else:
            state.key_map = None

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
    """Stop AudioStream if running."""
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


def switch_plugin(plugin_name: str, input_device: str, output_device: str) -> str:
    """Switch plugin — stop current stream and start with new plugin."""
    return _start_stream(plugin_name, input_device, output_device)


def search_tone(text: str) -> tuple[str, str]:
    """Search the anchor database for matching tones.

    New-search resets refinement state (any loaded tone is still audible, but
    the refine box starts fresh against whatever the user applies next).
    """
    if state.plugin is None:
        return "No plugin loaded.", ""
    if not text.strip():
        return "Enter a tone description.", ""

    results = state.engine.query(text, top_k=5, plugin_name=state.plugin_name)
    state.last_results = results

    if not results:
        return "No matches found.", ""

    lines = []
    for i, r in enumerate(results):
        lines.append(f"[{i+1}] {r['preset_name']}  (score: {r['score']:.3f})")
    display = "\n".join(lines)

    return f"Found {len(results)} matches. Click a number to apply, or click 'Blend All'.", display


def refine_tone(text: str) -> str:
    """Apply a delta command to the currently loaded tone.

    Refinement operates on the live plugin state — reads current params,
    adds the parsed delta, writes back. Requires a tone to be loaded first.
    """
    if state.plugin is None:
        return "No plugin loaded."
    if not state.tone_loaded:
        return "Load a tone first (search and apply a match), then refine."
    if not text.strip():
        return "Enter a refinement command."

    deltas = parse_deltas(text)
    if not deltas:
        keywords = ", ".join(sorted(recognized_keywords())[:20])
        return (
            f"Couldn't parse: '{text}'.\n"
            f"Try: brighter, darker, warmer, more gain, less fizzy, add delay, ...\n"
            f"Recognized keywords include: {keywords}, ..."
        )

    stats = apply_delta(state.plugin, deltas)
    lines = [f"Refined: {text}"]
    for change in stats["changes"]:
        lines.append(f"  {change}")
    if stats["skipped"]:
        lines.append(f"  ({stats['skipped']} params not available on this plugin)")
    return "\n".join(lines)


def apply_choice(choice: int) -> str:
    """Apply a specific match by loading the raw factory preset (lossless)."""
    if state.plugin is None:
        return "No plugin loaded."
    if not state.last_results:
        return "No search results. Search first."
    if choice < 0 or choice >= len(state.last_results):
        return f"Invalid choice: {choice+1}"

    result = state.last_results[choice]
    preset_path = result.get("preset_path")

    if not (preset_path and state.key_map and Path(preset_path).exists()):
        return f"Preset file not found: {preset_path}"

    stats = load_preset(state.plugin, preset_path, state.key_map)
    state.current_tone = None  # raw preset, no canonical representation
    state.tone_loaded = True
    return (
        f"Applied: {result['preset_name']} (raw preset, {stats['applied']} params)\n"
        f"  Full factory preset loaded — all parameters preserved."
    )


def apply_blended() -> str:
    """Apply weighted blend of all search results using raw preset params."""
    if state.plugin is None:
        return "No plugin loaded."
    if not state.last_results:
        return "No search results. Search first."

    import math

    preset_paths = []
    weights = []
    names = []
    for r in state.last_results:
        path = r.get("preset_path")
        if path and state.key_map and Path(path).exists():
            preset_paths.append(path)
            weights.append(math.exp(-(1 - r["score"])))
            names.append(r["preset_name"])

    if not preset_paths:
        return "No preset files found for blending."

    stats = blend_presets(state.plugin, preset_paths, weights, state.key_map)
    state.current_tone = None
    state.tone_loaded = True
    presets_str = ", ".join(names[:3])
    return (
        f"Applied: raw blend from {len(preset_paths)} presets ({presets_str}...)\n"
        f"  {stats['applied']} params blended, {stats['failed']} failed."
    )


# ── Gradio UI ────────────────────────────────────────────────────────

def build_ui():
    installed = get_installed_plugins()
    inputs, outputs = get_audio_devices()

    if not installed:
        raise RuntimeError("No Neural DSP plugins found.")

    with gr.Blocks(title="Neural DSP NLP Controller") as app:
        gr.Markdown("# Neural DSP NLP Controller\n"
                     "Type your tone, hear it live through your guitar.")

        # Audio setup (collapsed — auto-started, change only if needed)
        with gr.Accordion("Audio Settings", open=False):
            with gr.Row():
                plugin_dd = gr.Dropdown(choices=installed, value=state.plugin_name or installed[0], label="Plugin")
                input_dd = gr.Dropdown(choices=inputs, value=inputs[0] if inputs else None, label="Audio Input")
                output_dd = gr.Dropdown(choices=outputs, value=outputs[0] if outputs else None, label="Audio Output")
            switch_btn = gr.Button("Restart Audio")
            audio_status = gr.Textbox(label="Audio Status", interactive=False,
                                       value=f"Streaming: {state.plugin_name}" if state.plugin else "Not streaming")

        switch_btn.click(fn=switch_plugin, inputs=[plugin_dd, input_dd, output_dd], outputs=audio_status)

        gr.Markdown("---")
        gr.Markdown("## 1. Search for a tone")

        tone_input = gr.Textbox(
            label="Describe a tone",
            placeholder="warm blues crunch, ambient shimmer, 80s chorus clean...",
            lines=1,
        )
        search_btn = gr.Button("Search", variant="primary")

        search_status = gr.Textbox(label="Status", interactive=False)
        results_display = gr.Textbox(label="Matches (click a number to apply)", interactive=False, lines=6)

        search_btn.click(fn=search_tone, inputs=tone_input, outputs=[search_status, results_display])
        tone_input.submit(fn=search_tone, inputs=tone_input, outputs=[search_status, results_display])

        with gr.Row():
            btn1 = gr.Button("1")
            btn2 = gr.Button("2")
            btn3 = gr.Button("3")
            btn4 = gr.Button("4")
            btn5 = gr.Button("5")
            blend_btn = gr.Button("Blend All", variant="secondary")

        applied_display = gr.Textbox(label="Applied Tone", interactive=False, lines=4)

        btn1.click(fn=lambda: apply_choice(0), outputs=applied_display)
        btn2.click(fn=lambda: apply_choice(1), outputs=applied_display)
        btn3.click(fn=lambda: apply_choice(2), outputs=applied_display)
        btn4.click(fn=lambda: apply_choice(3), outputs=applied_display)
        btn5.click(fn=lambda: apply_choice(4), outputs=applied_display)
        blend_btn.click(fn=apply_blended, outputs=applied_display)

        gr.Markdown("---")
        gr.Markdown("## 2. Refine the loaded tone")
        gr.Markdown(
            "*Adjust the currently-playing tone with delta commands — "
            "no re-search. Examples: `brighter`, `darker`, `more gain`, "
            "`less fizzy`, `add delay`, `a bit warmer`.*"
        )

        refine_input = gr.Textbox(
            label="Refinement command",
            placeholder="brighter, more gain, less fizzy...",
            lines=1,
        )
        refine_btn = gr.Button("Refine", variant="primary")
        refine_display = gr.Textbox(label="Refinement Result", interactive=False, lines=4)

        refine_btn.click(fn=refine_tone, inputs=refine_input, outputs=refine_display)
        refine_input.submit(fn=refine_tone, inputs=refine_input, outputs=refine_display)

    return app


# ── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    installed = get_installed_plugins()
    if not installed:
        print("ERROR: No Neural DSP plugins found.")
        sys.exit(1)

    inputs, outputs = get_audio_devices()
    if not inputs or not outputs:
        print("ERROR: No audio devices found. Connect an audio interface.")
        sys.exit(1)

    # Load NLP engine on main thread
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

    # Auto-start audio (loads one plugin instance on main thread)
    plugin_name = installed[0]
    input_device = inputs[0]
    output_device = outputs[0]
    print(f"Starting audio: {input_device} -> {plugin_name} -> {output_device}")
    result = _start_stream(plugin_name, input_device, output_device)
    print(f"  {result}")

    # Launch Gradio in background thread, main thread serves plugin loads
    app = build_ui()
    app.launch(theme=gr.themes.Soft(), prevent_thread_lock=True)
    print("Main thread ready for plugin load requests.")
    _main_thread_loader_loop()
