"""Neural DSP NLP Controller — Real-time standalone app.

Type a tone description, hear it through your guitar in real-time.

Usage:
  uv run python app.py

Requires: Audio interface connected, at least one Neural DSP Archetype plugin installed.
"""

import sys
from pathlib import Path

import gradio as gr
from pedalboard import Pedalboard, load_plugin
from pedalboard.io import AudioStream

from neuraldsp_nlp_controller.adapter import apply
from neuraldsp_nlp_controller.nlp_engine import NLPEngine

# ── Configuration ────────────────────────────────────────────────────

ANCHOR_PATH = Path(__file__).parent / "data" / "anchors.yaml"
SAMPLE_RATE = 44100
BUFFER_SIZE = 256

AVAILABLE_PLUGINS = {
    "Archetype Tim Henson X": "/Library/Audio/Plug-Ins/VST3/Archetype Tim Henson X.vst3",
    "Archetype Cory Wong X": "/Library/Audio/Plug-Ins/VST3/Archetype Cory Wong X.vst3",
}


# ── App State ────────────────────────────────────────────────────────

class AppState:
    def __init__(self):
        self.plugin = None
        self.plugin_name = ""
        self.stream = None
        self.board = None
        self.engine = None
        self.current_tone = None
        # Cache last query results so user can click to apply any of them
        self.last_results: list[dict] = []


state = AppState()


# ── Core Functions ───────────────────────────────────────────────────

def get_installed_plugins() -> list[str]:
    return [name for name, path in AVAILABLE_PLUGINS.items()
            if Path(path).exists()]


def get_audio_devices() -> tuple[list[str], list[str]]:
    return list(AudioStream.input_device_names), list(AudioStream.output_device_names)


def _start_stream(plugin_name: str, input_device: str, output_device: str) -> str:
    """Load plugin on main thread and start AudioStream."""
    _stop_stream()

    vst3_path = AVAILABLE_PLUGINS.get(plugin_name)
    if not vst3_path:
        return f"Plugin not found: {plugin_name}"

    try:
        # Load plugin on main thread to avoid thread-safety issues
        state.plugin = load_plugin(vst3_path)
        state.plugin_name = plugin_name
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
    state.current_tone = None
    state.last_results = []


def switch_plugin(plugin_name: str, input_device: str, output_device: str) -> str:
    """Switch plugin — restart stream with new plugin."""
    return _start_stream(plugin_name, input_device, output_device)


def search_tone(text: str) -> tuple[str, str]:
    """Search for matching tones. Returns (status, results_display).

    Does NOT auto-apply — shows top 5 for user to choose from.
    """
    if state.plugin is None:
        return "No plugin loaded.", ""
    if not text.strip():
        return "Enter a tone description.", ""

    results = state.engine.query(text, top_k=5, plugin_name=state.plugin_name)
    state.last_results = results

    if not results:
        return "No matches found.", ""

    # Build results display
    lines = []
    for i, r in enumerate(results):
        lines.append(f"[{i+1}] {r['preset_name']}  (score: {r['score']:.3f})")
    display = "\n".join(lines)

    return f"Found {len(results)} matches. Click a number to apply, or click 'Apply Blended'.", display


def apply_choice(choice: int) -> str:
    """Apply a specific match from the last search results."""
    if state.plugin is None:
        return "No plugin loaded."
    if not state.last_results:
        return "No search results. Search first."
    if choice < 0 or choice >= len(state.last_results):
        return f"Invalid choice: {choice+1}"

    result = state.last_results[choice]
    from neuraldsp_nlp_controller.nlp_engine import _dict_to_tone
    tone = _dict_to_tone(result["tone"])
    tone.plugin_name = result["plugin_name"]
    tone.preset_name = result["preset_name"]
    state.current_tone = tone

    stats = apply(state.plugin, tone)
    return (
        f"Applied: {result['preset_name']} (exact)\n"
        f"  Amp: {tone.amp.character}  gain={tone.amp.gain:.2f}  "
        f"bass={tone.amp.bass:.2f}  mid={tone.amp.mid:.2f}  "
        f"treble={tone.amp.treble:.2f}\n"
        + _effects_line(tone)
    )


def apply_blended() -> str:
    """Apply interpolated blend of all search results."""
    if state.plugin is None:
        return "No plugin loaded."
    if not state.last_results:
        return "No search results. Search first."

    from neuraldsp_nlp_controller.nlp_engine import _interpolate
    tone = _interpolate(state.last_results, sensitivity=1.0)
    state.current_tone = tone

    stats = apply(state.plugin, tone)
    presets = ", ".join(r["preset_name"] for r in state.last_results[:3])
    return (
        f"Applied: blended from {len(state.last_results)} matches ({presets}...)\n"
        f"  Amp: {tone.amp.character}  gain={tone.amp.gain:.2f}  "
        f"bass={tone.amp.bass:.2f}  mid={tone.amp.mid:.2f}  "
        f"treble={tone.amp.treble:.2f}\n"
        + _effects_line(tone)
    )


def _effects_line(tone) -> str:
    effects = []
    if tone.overdrive.active:
        effects.append(f"OD (drive={tone.overdrive.drive:.2f})")
    if tone.compressor.active:
        effects.append(f"Comp ({tone.compressor.compression:.2f})")
    if tone.chorus.active:
        effects.append(f"Chorus (mix={tone.chorus.mix:.2f})")
    if tone.delay.active:
        effects.append(f"Delay (mix={tone.delay.mix:.2f})")
    if tone.reverb.active:
        effects.append(f"Reverb (mix={tone.reverb.mix:.2f})")
    return "  Effects: " + (" | ".join(effects) if effects else "none")


# ── Gradio UI ────────────────────────────────────────────────────────

def build_ui():
    installed = get_installed_plugins()
    inputs, outputs = get_audio_devices()

    if not installed:
        raise RuntimeError("No Neural DSP plugins found.")

    with gr.Blocks(title="Neural DSP NLP Controller", theme=gr.themes.Soft()) as app:
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

        # Tone search
        tone_input = gr.Textbox(
            label="Describe your tone",
            placeholder="warm blues crunch, ambient shimmer, 80s chorus clean...",
            lines=1,
        )
        search_btn = gr.Button("Search", variant="primary")

        search_status = gr.Textbox(label="Status", interactive=False)
        results_display = gr.Textbox(label="Matches (click a number to apply)", interactive=False, lines=6)

        search_btn.click(fn=search_tone, inputs=tone_input, outputs=[search_status, results_display])
        tone_input.submit(fn=search_tone, inputs=tone_input, outputs=[search_status, results_display])

        # Apply buttons
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
    print("Loading NLP engine...")
    state.engine = NLPEngine(ANCHOR_PATH)
    print(f"  {len(state.engine.anchors)} anchors loaded.")

    # Auto-start audio on main thread (avoids thread-safety error)
    plugin_name = installed[0]
    input_device = inputs[0]
    output_device = outputs[0]
    print(f"Starting audio: {input_device} -> {plugin_name} -> {output_device}")
    result = _start_stream(plugin_name, input_device, output_device)
    print(f"  {result}")

    # Launch UI
    app = build_ui()
    app.launch()
