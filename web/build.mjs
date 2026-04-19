// Concatenate JSX sources and feed them to esbuild as one module.
// We do this rather than real ES imports because the existing code uses
// shared globals (window.getTheme, window.api, etc.) — simpler than
// refactoring to imports for a single-page app this small.
//
// React and ReactDOM are loaded separately via <script> tags and come in as
// globals, so they are NOT bundled here.

import { build } from 'esbuild';
import { readFile, writeFile, mkdir } from 'node:fs/promises';

const sources = ['src/api.js', 'src/app.jsx', 'src/shell.jsx'];
const parts = await Promise.all(sources.map(p => readFile(p, 'utf8')));
const combined = parts.join('\n\n');

const result = await build({
  stdin: {
    contents: combined,
    loader: 'jsx',
    resolveDir: process.cwd(),
    sourcefile: 'bundle-entry.jsx',
  },
  bundle: false,          // Nothing to resolve — no imports.
  write: false,
  format: 'iife',
  target: ['es2020'],
  jsx: 'transform',
  jsxFactory: 'React.createElement',
  jsxFragment: 'React.Fragment',
  minify: true,
  logLevel: 'info',
});

await mkdir('static', { recursive: true });
await writeFile('static/bundle.js', result.outputFiles[0].contents);
console.log(`wrote static/bundle.js (${result.outputFiles[0].contents.length} bytes)`);
