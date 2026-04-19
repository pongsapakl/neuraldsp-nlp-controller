# Web UI

Precompiled React bundle served by `server.py` at `/`.

## Rebuild after editing `src/*.jsx`

```bash
cd web && node build.mjs
```

No install step needed at runtime. `static/bundle.js` is checked in so the app
runs without Node. The esbuild dependency is only for rebuilds.

## Layout

- `index.html` — loads React UMD + `bundle.js`
- `src/api.js` — fetch wrappers around `/api/*`
- `src/app.jsx` — primitive components (theme, tone bars, search input, match card)
- `src/shell.jsx` — container: state, routing, API calls, page shell
- `static/react.production.min.js` + `static/react-dom.production.min.js` — vendored React 18 UMD
- `static/bundle.js` — build output (committed)
- `build.mjs` — concatenates JSX sources, transforms via esbuild, writes `static/bundle.js`
