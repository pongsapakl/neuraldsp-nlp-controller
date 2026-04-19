// Thin fetch wrappers for the FastAPI backend.
// All failures throw Error(message). Callers render message as-is.

async function req(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : {};
  if (!res.ok) throw new Error(data.error || `${method} ${path} ${res.status}`);
  return data;
}

const api = {
  state:   ()                => req('GET',  '/api/state'),
  devices: ()                => req('GET',  '/api/devices'),
  setDevs: (plugin, i, o)    => req('POST', '/api/devices', { plugin, input: i, output: o }),
  search:  (text)            => req('POST', '/api/search',  { text }),
  apply:   (index)           => req('POST', '/api/apply',   { index }),
  blend:   ()                => req('POST', '/api/blend',   {}),
  refine:  (text)            => req('POST', '/api/refine',  { text }),
};

window.api = api;
