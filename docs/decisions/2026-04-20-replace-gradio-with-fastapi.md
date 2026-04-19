# Replace Gradio with FastAPI + precompiled React

Date: 2026-04-20
Status: Accepted

## Context

The NLP engine, adapter, preset loader, and main-thread VST3 loader all work
well. The only weak link was the Gradio UI — it looked like a dev tool, made
the app feel unfinished, and coupled audio status, search, apply, and refine
into one cluttered page. A custom UI was designed in Claude Design and handed
over as a React prototype (`1P Landing.html` + `app.jsx` + `shell.jsx`).

We had to pick how to serve it without giving up the product's core constraints:

- **Local-first** — no network calls at runtime (including for the UI itself).
- **Low-resource** — the app already coexists with a DAW, a VST3 plugin, and
  real-time audio on a single laptop. The UI layer should be ~kilobytes, not
  megabytes.
- **Main-thread VST3 loading** — macOS requires plugins to be created on the
  main thread. Whatever serves HTTP must run in a worker thread.

## Decision

1. Replace Gradio with **FastAPI + uvicorn**. FastAPI handles the JSON API;
   uvicorn runs in a background thread. The main thread keeps
   `_main_thread_loader_loop()`.
2. Ship the UI as **precompiled JSX + vendored React UMD**, served from
   `/static/`. No CDN, no in-browser Babel, no npm install at runtime. One
   `node build.mjs` command turns `src/*.jsx` into `static/bundle.js`.
3. Bind to **127.0.0.1:7860**. Local only. Same port Gradio used so muscle
   memory survives.
4. `app.py` stays the entry point, but it's now a thin shim: boot engine,
   start stream, launch uvicorn in a background thread, park the main thread
   on the loader loop. `server.py` owns the FastAPI app and the endpoints.

## Reasons

- **Gradio is a prototyping tool, not a product UI.** We've outgrown it. The
  custom design fits the product (tone-bar previews, confidence tiers,
  dedicated refine surface) in a way Gradio can't.
- **FastAPI is the smallest step away from Gradio** that gets us full UI
  control without introducing a separate frontend service, build pipeline,
  or deployment target. Everything still ships as one `python app.py`.
- **Precompiled bundle + vendored React = zero network dependency.** The
  total UI payload (React UMD + bundle) is ~165KB uncompressed, ~50KB gzipped.
  That's smaller than Gradio's runtime footprint and it works with wifi off.
- **esbuild over a real bundler.** No imports inside the JSX — the three
  source files share globals (`window.api`, `window.getTheme`, etc.), which
  is acceptable for a single-page app this small. esbuild just concatenates,
  transforms JSX, and minifies. Build is sub-second.

## Rejected alternatives

- **Streamlit / NiceGUI** — same category as Gradio. Swapping one opinionated
  dev-tool UI for another doesn't solve the "feels like a dev tool" problem.
- **Next.js / Vite / full SPA build** — too much ceremony for a single page.
  Would require a second process (or a static-export + FastAPI setup) and a
  much heavier bundle. Precompiled JSX + UMD React was the minimum viable.
- **In-browser Babel from CDN** — contradicts local-first. Would fail with
  wifi off and pay startup cost on every page load.
- **WebSocket live state instead of polling** — overkill for this UI. The
  only state that needs to be live is "is the anchor DB being built?" and a
  3s poll during that narrow state is fine. Normal operation is
  request/response (search, apply, refine), which maps cleanly to REST.

## Consequences

- New runtime deps: `fastapi`, `uvicorn[standard]`. Removed: `gradio`.
- New dev dep (for UI rebuilds only): `esbuild`.
- The `web/` directory becomes part of the source tree; `web/static/bundle.js`
  is committed so the app runs without Node installed.
- `server.py` is new; `app.py` is refactored to be much shorter.
- The handoff directory (`neural-dsp-nlp-controller/`) and zip are deleted —
  their content lives in `web/` now.
