"""Neural DSP NLP Controller — Real-time standalone app.

Type a tone description, hear it through your guitar in real-time.

Usage:
  uv run python app.py

Requires: Audio interface connected, at least one Neural DSP Archetype plugin installed.
"""

import threading
import time
from pathlib import Path

import gradio as gr
from pedalboard import Pedalboard, load_plugin
from pedalboard.io import AudioStream

from neuraldsp_nlp_controller.adapter import apply, extract
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
        self.history: list[dict] = []
        self.current_tone = None

    def is_streaming(self) -> bool:
        return self.stream is not None


state = AppState()


# ── Core Functions ───────────────────────────────────────────────────

def get_installed_plugins() -> list[str]:
    """Detect which Neural DSP plugins are installed."""
    return [name for name, path in AVAILABLE_PLUGINS.items()
            if Path(path).exists()]


def get_audio_devices() -> tuple[list[str], list[str]]:
    """Get available audio input/output devices."""
    return list(AudioStream.input_device_names), list(AudioStream.output_device_names)


def load_engine():
    """Load NLP engine (lazy, once)."""
    if state.engine is None:
        state.engine = NLPEngine(ANCHOR_PATH)
    return state.engine


def start_audio(plugin_name: str, input_device: str, output_device: str) -> str:
    """Load plugin and start AudioStream."""
    if state.is_streaming():
        return "Already streaming. Stop first."

    vst3_path = AVAILABLE_PLUGINS.get(plugin_name)
    if not vst3_path:
        return f"Plugin not found: {plugin_name}"

    try:
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
        return f"Failed to start: {e}"


def stop_audio() -> str:
    """Stop AudioStream."""
    if not state.is_streaming():
        return "Not streaming."
    try:
        state.stream.__exit__(None, None, None)
    except Exception:
        pass
    state.stream = None
    state.plugin = None
    state.board = None
    state.plugin_name = ""
    state.history = []
    state.current_tone = None
    return "Stopped."


def describe_tone(text: str) -> tuple[str, str, str]:
    """Process a tone description: NLP match → apply to plugin.

    Returns (status, match_info, tone_details).
    """
    if not state.is_streaming():
        return "Not streaming. Start audio first.", "", ""
    if not text.strip():
        return "Enter a tone description.", "", ""

    engine = load_engine()

    tone, info = engine.match(
        text,
        top_k=5,
        sensitivity=1.0,
        plugin_name=state.plugin_name,
    )
    state.current_tone = tone

    # Apply to plugin
    result = apply(state.plugin, tone)

    # Build display strings
    match_display = (
        f"Best match: {info['preset_name']} (score: {info['score']:.3f})\n"
    )
    if "top_matches" in info:
        match_display += f"Blended from {info['interpolated_from']} anchors:\n"
        for m in info["top_matches"]:
            match_display += f"  {m['score']:.3f}  {m['preset']}\n"

    tone_display = (
        f"Amp: {tone.amp.character}  "
        f"gain={tone.amp.gain:.2f}  bass={tone.amp.bass:.2f}  "
        f"mid={tone.amp.mid:.2f}  treble={tone.amp.treble:.2f}  "
        f"presence={tone.amp.presence:.2f}\n"
    )
    effects = []
    if tone.overdrive.active:
        effects.append(f"OD (drive={tone.overdrive.drive:.2f})")
    if tone.compressor.active:
        effects.append(f"Comp ({tone.compressor.compression:.2f})")
    if tone.chorus.active:
        effects.append(f"Chorus (mix={tone.chorus.mix:.2f})")
    if tone.delay.active:
        effects.append(f"Delay (time={tone.delay.time:.2f} mix={tone.delay.mix:.2f})")
    if tone.reverb.active:
        effects.append(f"Reverb (size={tone.reverb.size:.2f} mix={tone.reverb.mix:.2f})")
    if effects:
        tone_display += "Effects: " + " | ".join(effects)
    else:
        tone_display += "Effects: none active"

    # Track history
    state.history.append({"text": text, "preset": info["preset_name"], "score": info["score"]})

    status = f"Applied ({result['applied']} params set, {result['skipped']} skipped)"
    return status, match_display, tone_display


# ── Gradio UI ────────────────────────────────────────────────────────

def build_ui():
    installed = get_installed_plugins()
    inputs, outputs = get_audio_devices()

    if not installed:
        raise RuntimeError(
            "No Neural DSP plugins found. Install at least one Archetype plugin."
        )

    with gr.Blocks(title="Neural DSP NLP Controller", theme=gr.themes.Soft()) as app:
        gr.Markdown("# Neural DSP NLP Controller\n"
                     "Type your tone, hear it live through your guitar.")

        # Audio setup
        with gr.Row():
            with gr.Column(scale=1):
                plugin_dd = gr.Dropdown(
                    choices=installed,
                    value=installed[0],
                    label="Plugin",
                )
            with gr.Column(scale=1):
                input_dd = gr.Dropdown(
                    choices=inputs,
                    value=inputs[0] if inputs else None,
                    label="Audio Input",
                )
            with gr.Column(scale=1):
                output_dd = gr.Dropdown(
                    choices=outputs,
                    value=outputs[0] if outputs else None,
                    label="Audio Output",
                )

        with gr.Row():
            start_btn = gr.Button("Start Audio", variant="primary")
            stop_btn = gr.Button("Stop Audio", variant="stop")
            audio_status = gr.Textbox(label="Audio Status", interactive=False)

        start_btn.click(
            fn=start_audio,
            inputs=[plugin_dd, input_dd, output_dd],
            outputs=audio_status,
        )
        stop_btn.click(fn=stop_audio, outputs=audio_status)

        gr.Markdown("---")

        # Tone input
        tone_input = gr.Textbox(
            label="Describe your tone",
            placeholder="warm blues crunch, ambient shimmer, 80s chorus clean...",
            lines=1,
        )
        submit_btn = gr.Button("Apply Tone", variant="primary")

        # Results
        apply_status = gr.Textbox(label="Status", interactive=False)
        with gr.Row():
            match_info = gr.Textbox(label="Match Info", interactive=False, lines=6)
            tone_details = gr.Textbox(label="Current Tone", interactive=False, lines=4)

        submit_btn.click(
            fn=describe_tone,
            inputs=tone_input,
            outputs=[apply_status, match_info, tone_details],
        )
        tone_input.submit(
            fn=describe_tone,
            inputs=tone_input,
            outputs=[apply_status, match_info, tone_details],
        )

    return app


# ── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Loading NLP engine...")
    load_engine()
    print(f"Ready. {len(state.engine.anchors)} anchors loaded.")

    app = build_ui()
    app.launch()
