"""FastAPI server for the Neural DSP NLP Controller.

Serves the precompiled React UI at / and a thin JSON API that wraps the
backend functions in app.py. Uvicorn runs in a background thread so that
the main thread stays free for VST3 plugin loads (macOS/Cocoa requirement).
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import app as backend


WEB_DIR = Path(__file__).parent / "web"
STATIC_DIR = WEB_DIR / "static"
INDEX_HTML = WEB_DIR / "index.html"


# ── Request bodies ──────────────────────────────────────────────────

class DevicesBody(BaseModel):
    plugin: str
    input: str
    output: str


class SearchBody(BaseModel):
    text: str


class ApplyBody(BaseModel):
    index: int


class RefineBody(BaseModel):
    text: str


# ── Helpers ─────────────────────────────────────────────────────────

def _derive_chars(tone: dict) -> dict:
    """Pick 6 canonical fields for the UI's tone-bars display.

    Keep this in sync with web/src/app.jsx — the order is assumed.
    """
    return {
        "gain": tone["amp"]["gain"],
        "bass": tone["amp"]["bass"],
        "mid":  tone["amp"]["mid"],
        "treb": tone["amp"]["treble"],
        "verb": tone["reverb"]["mix"]  if tone["reverb"]["active"] else 0.0,
        "dly":  tone["delay"]["mix"]   if tone["delay"]["active"]  else 0.0,
    }


def _anchor_count() -> int:
    return len(backend.state.engine.anchors) if backend.state.engine else 0


def _app_state() -> str:
    if not backend.get_installed_plugins():
        return "no-plugin"
    if not backend.ANCHOR_PATH.exists():
        return "building"
    return "ready"


# ── FastAPI app ─────────────────────────────────────────────────────

def build_app() -> FastAPI:
    app = FastAPI(title="Neural DSP NLP Controller", docs_url=None, redoc_url=None)

    @app.get("/api/state")
    def get_state():
        return {
            "plugin_name":  backend.state.plugin_name,
            "streaming":    backend.state.stream is not None,
            "anchor_count": _anchor_count(),
            "tone_loaded":  backend.state.tone_loaded,
            "app_state":    _app_state(),
        }

    @app.get("/api/devices")
    def get_devices():
        inputs, outputs = backend.get_audio_devices()
        return {
            "plugins":        backend.get_installed_plugins(),
            "current_plugin": backend.state.plugin_name,
            "inputs":         inputs,
            "current_input":  backend.state.input_device,
            "outputs":        outputs,
            "current_output": backend.state.output_device,
        }

    @app.post("/api/devices")
    def post_devices(body: DevicesBody):
        status = backend.switch_plugin(body.plugin, body.input, body.output)
        if backend.state.stream is None:
            raise HTTPException(status_code=400, detail={"error": status})
        return {"status": status}

    @app.post("/api/search")
    def post_search(body: SearchBody):
        if backend.state.plugin is None:
            raise HTTPException(status_code=400, detail={"error": "No plugin loaded"})
        text = body.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail={"error": "Empty query"})

        results = backend.state.engine.query(text, top_k=5,
                                              plugin_name=backend.state.plugin_name)
        backend.state.last_results = results

        out = []
        for r in results:
            preset_path = r.get("preset_path") or ""
            out.append({
                "id":    r["preset_name"],
                "name":  r["preset_name"],
                "plugin": r["plugin_name"],
                "score":  r["score"],
                "desc":   r["description"],
                "tags":   [],
                "chars":  _derive_chars(r["tone"]),
                "preset_path_present": bool(preset_path and Path(preset_path).exists()),
            })
        return {"query": text, "anchor_count": _anchor_count(), "results": out}

    @app.post("/api/apply")
    def post_apply(body: ApplyBody):
        if backend.state.plugin is None:
            raise HTTPException(status_code=400, detail={"error": "No plugin loaded"})
        if not backend.state.last_results:
            raise HTTPException(status_code=400, detail={"error": "No search results"})
        if body.index < 0 or body.index >= len(backend.state.last_results):
            raise HTTPException(status_code=400, detail={"error": f"Invalid index {body.index}"})

        result = backend.state.last_results[body.index]
        preset_path = result.get("preset_path")
        if not (preset_path and backend.state.key_map and Path(preset_path).exists()):
            raise HTTPException(status_code=400,
                                detail={"error": f"Preset file not found: {preset_path}"})

        from neuraldsp_nlp_controller.preset_loader import load_preset
        stats = load_preset(backend.state.plugin, preset_path, backend.state.key_map)
        backend.state.current_tone = None
        backend.state.tone_loaded = True
        return {
            "applied":        result["preset_name"],
            "params_applied": stats["applied"],
            "tone_loaded":    True,
        }

    @app.post("/api/blend")
    def post_blend():
        import math
        from neuraldsp_nlp_controller.preset_loader import blend_presets

        if backend.state.plugin is None:
            raise HTTPException(status_code=400, detail={"error": "No plugin loaded"})
        if not backend.state.last_results:
            raise HTTPException(status_code=400, detail={"error": "No search results"})

        paths, weights, names = [], [], []
        for r in backend.state.last_results:
            p = r.get("preset_path")
            if p and backend.state.key_map and Path(p).exists():
                paths.append(p)
                weights.append(math.exp(-(1 - r["score"])))
                names.append(r["preset_name"])

        if not paths:
            raise HTTPException(status_code=400,
                                detail={"error": "No preset files found for blending"})

        stats = blend_presets(backend.state.plugin, paths, weights, backend.state.key_map)
        backend.state.current_tone = None
        backend.state.tone_loaded = True
        return {
            "applied":        f"Blend of top {len(paths)}",
            "params_applied": stats["applied"],
            "params_failed":  stats["failed"],
            "tone_loaded":    True,
        }

    @app.post("/api/refine")
    def post_refine(body: RefineBody):
        from neuraldsp_nlp_controller.adapter import apply_delta
        from neuraldsp_nlp_controller.refinement import parse_deltas

        if backend.state.plugin is None:
            raise HTTPException(status_code=400, detail={"error": "No plugin loaded"})
        if not backend.state.tone_loaded:
            raise HTTPException(status_code=400,
                                detail={"error": "Load a tone first, then refine"})
        text = body.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail={"error": "Empty command"})

        deltas = parse_deltas(text)
        if not deltas:
            raise HTTPException(status_code=400,
                                detail={"error": f"Couldn't parse: '{text}'"})

        stats = apply_delta(backend.state.plugin, deltas)
        return {
            "ok":      True,
            "message": f"Refined: {text}",
            "changes": stats["changes"],
            "skipped": stats["skipped"],
        }

    # Static UI (mounted last so API routes win)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def index():
        return FileResponse(INDEX_HTML)

    return app
