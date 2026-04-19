// Tone Controller — main container. Drives UI from /api/state and /api/devices.

const { useState: useStateA, useEffect: useEffectA } = React;

function ToneController() {
  const theme = getTheme();

  // Server-derived state
  const [appState, setAppState] = useStateA('loading'); // loading | no-plugin | building | ready
  const [anchorCount, setAnchorCount] = useStateA(0);
  const [streaming, setStreaming] = useStateA(false);
  const [plugin, setPlugin] = useStateA('');

  // Devices
  const [plugins, setPlugins] = useStateA([]);
  const [inputs, setInputs] = useStateA([]);
  const [outputs, setOutputs] = useStateA([]);
  const [inputDevice, setInputDevice] = useStateA('');
  const [outputDevice, setOutputDevice] = useStateA('');

  // Search & apply
  const [query, setQuery] = useStateA('');
  const [lastQuery, setLastQuery] = useStateA('');
  const [results, setResults] = useStateA([]);
  const [searching, setSearching] = useStateA(false);
  const [applied, setApplied] = useStateA(null);    // preset id | '__blend__' | null
  const [appliedName, setAppliedName] = useStateA('');
  const [refineHistory, setRefineHistory] = useStateA([]);
  const [refineInput, setRefineInput] = useStateA('');
  const [showSettings, setShowSettings] = useStateA(false);
  const [error, setError] = useStateA('');

  const refreshState = async () => {
    try {
      const s = await api.state();
      setAppState(s.app_state);
      setAnchorCount(s.anchor_count);
      setStreaming(s.streaming);
      setPlugin(s.plugin_name);
      if (!s.tone_loaded) {
        setApplied(null);
        setAppliedName('');
        setRefineHistory([]);
      }
    } catch (e) { setError(e.message); }
  };

  const refreshDevices = async () => {
    try {
      const d = await api.devices();
      setPlugins(d.plugins);
      setInputs(d.inputs);
      setOutputs(d.outputs);
      setPlugin(d.current_plugin);
      setInputDevice(d.current_input);
      setOutputDevice(d.current_output);
    } catch (e) { setError(e.message); }
  };

  useEffectA(() => {
    refreshState();
    refreshDevices();
  }, []);

  // Poll while building so UI picks up "ready" when anchors land.
  useEffectA(() => {
    if (appState !== 'building') return;
    const id = setInterval(refreshState, 3000);
    return () => clearInterval(id);
  }, [appState]);

  const runSearch = async (q) => {
    const text = (q ?? query).trim();
    if (!text) return;
    setLastQuery(text);
    setSearching(true);
    setResults([]);
    setApplied(null);
    setAppliedName('');
    setRefineHistory([]);
    setError('');
    try {
      const r = await api.search(text);
      setResults(r.results);
      setAnchorCount(r.anchor_count);
    } catch (e) {
      setError(e.message);
    } finally {
      setSearching(false);
    }
  };

  const applyPreset = async (id) => {
    const idx = results.findIndex(r => r.id === id);
    if (idx < 0) return;
    try {
      const r = await api.apply(idx);
      setApplied(id);
      setAppliedName(r.applied);
      setRefineHistory([]);
    } catch (e) { setError(e.message); }
  };

  const applyBlend = async () => {
    try {
      const r = await api.blend();
      setApplied('__blend__');
      setAppliedName(r.applied);
      setRefineHistory([]);
    } catch (e) { setError(e.message); }
  };

  const runRefine = async (chip) => {
    const text = (chip ?? refineInput).trim();
    if (!text || !applied) return;
    try {
      const r = await api.refine(text);
      setRefineHistory(h => [...h, { text: r.message || text, ts: Date.now() }]);
      setRefineInput('');
    } catch (e) { setError(e.message); }
  };

  const switchDevices = async () => {
    try {
      await api.setDevs(plugin, inputDevice, outputDevice);
      await refreshState();
      setApplied(null); setAppliedName(''); setResults([]); setLastQuery('');
    } catch (e) { setError(e.message); }
  };

  const fontImports = (
    <style>{`
      @keyframes livePulse { 0% { transform: scale(1); opacity: 0.7; } 100% { transform: scale(2.5); opacity: 0; } }
      @keyframes bar { 0%, 100% { transform: scaleY(0.3); } 50% { transform: scaleY(1); } }
      @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
      .match-enter { animation: fadeIn 0.32s cubic-bezier(.2,.8,.2,1) both; }
      input::placeholder, textarea::placeholder { color: ${theme.textFaint}; }
      * { box-sizing: border-box; }
      ::-webkit-scrollbar { width: 8px; height: 8px; }
      ::-webkit-scrollbar-track { background: transparent; }
      ::-webkit-scrollbar-thumb { background: ${theme.border}; border-radius: 4px; }
    `}</style>
  );

  return (
    <div style={{ minHeight: '100vh', background: theme.bg, color: theme.text,
                  fontFamily: theme.display, padding: '28px 24px 48px' }}>
      {fontImports}
      <div style={{ maxWidth: 820, margin: '0 auto', display: 'flex',
                    flexDirection: 'column', gap: 18 }}>
        <HeaderBar theme={theme} plugin={plugin} streaming={streaming}
                   onSettings={() => setShowSettings(!showSettings)}
                   settingsOpen={showSettings} />

        {showSettings && (
          <SettingsPanel
            theme={theme}
            plugin={plugin} setPlugin={setPlugin} plugins={plugins}
            inputDevice={inputDevice} setInputDevice={setInputDevice} inputs={inputs}
            outputDevice={outputDevice} setOutputDevice={setOutputDevice} outputs={outputs}
            onRestart={switchDevices} />
        )}

        {error && <ErrorBar theme={theme} message={error} onClose={() => setError('')} />}

        {appState === 'loading' && <LoadingState theme={theme} />}
        {appState === 'no-plugin' && <NoPluginState theme={theme} onRetry={refreshState} />}
        {appState === 'building' && <BuildingState theme={theme} anchorCount={anchorCount} />}

        {appState === 'ready' && (
          <>
            <SearchInput value={query} onChange={setQuery}
                         onSubmit={() => runSearch()} theme={theme} />

            {!lastQuery && !searching && (
              <EmptyState theme={theme} anchorCount={anchorCount}
                          onPick={(q) => { setQuery(q); runSearch(q); }} />
            )}

            {searching && <SearchingState theme={theme} query={query} anchorCount={anchorCount} />}

            {!searching && lastQuery && results.length > 0 && (
              <ResultsList results={results} theme={theme} applied={applied}
                           onApply={applyPreset} onBlend={applyBlend}
                           anchorCount={anchorCount} />
            )}

            {applied && (
              <RefineSection theme={theme} applied={applied}
                             appliedName={appliedName}
                             history={refineHistory}
                             input={refineInput} setInput={setRefineInput}
                             onRun={runRefine} />
            )}
          </>
        )}
      </div>
    </div>
  );
}

function HeaderBar({ theme, plugin, streaming, onSettings, settingsOpen }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 16,
                  paddingBottom: 20, borderBottom: `1px solid ${theme.border}` }}>
      <div style={{ width: 32, height: 32, borderRadius: 8,
                    border: `1.5px solid ${theme.accent}`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ width: 12, height: 12, background: theme.accent, borderRadius: '50%' }} />
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ fontFamily: theme.display, fontSize: 15, fontWeight: 600,
                      color: theme.text, letterSpacing: theme.displayTracking }}>
          Tone Controller
        </div>
        <div style={{ fontFamily: theme.mono, fontSize: 10, letterSpacing: '0.14em',
                      color: theme.textDim, marginTop: 2 }}>
          {(plugin || 'NEURAL DSP NLP').toUpperCase()}
        </div>
      </div>
      <LiveDot theme={theme} active={streaming} />
      <button onClick={onSettings} aria-label="Settings"
        style={{ width: 34, height: 34,
                 background: settingsOpen ? theme.accentSoft : 'transparent',
                 border: `1px solid ${settingsOpen ? theme.accent : theme.border}`,
                 borderRadius: Math.max(theme.radius - 2, 2),
                 color: settingsOpen ? theme.accent : theme.textDim,
                 cursor: 'pointer', display: 'flex', alignItems: 'center',
                 justifyContent: 'center', padding: 0 }}>
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none"
             stroke="currentColor" strokeWidth="1.5">
          <circle cx="7" cy="7" r="2"/>
          <path d="M7 1v2M7 11v2M13 7h-2M3 7H1M11.2 2.8l-1.4 1.4M4.2 9.8l-1.4 1.4M11.2 11.2l-1.4-1.4M4.2 4.2L2.8 2.8"/>
        </svg>
      </button>
    </div>
  );
}

function SettingsPanel({ theme, plugin, setPlugin, plugins,
                         inputDevice, setInputDevice, inputs,
                         outputDevice, setOutputDevice, outputs, onRestart }) {
  const Row = ({ label, value, options, onChange }) => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, flex: 1, minWidth: 180 }}>
      <div style={{ fontFamily: theme.mono, fontSize: 9, letterSpacing: '0.14em',
                    color: theme.textDim, fontWeight: 700 }}>{label}</div>
      <select value={value} onChange={(e) => onChange(e.target.value)}
        style={{ background: theme.card, border: `1px solid ${theme.border}`,
                 borderRadius: Math.max(theme.radius - 2, 2),
                 color: theme.text, padding: '9px 12px', fontSize: 13,
                 fontFamily: theme.display, outline: 'none', cursor: 'pointer' }}>
        {options.map(o => (
          <option key={o} value={o} style={{ background: theme.card }}>{o}</option>
        ))}
      </select>
    </div>
  );
  return (
    <div style={{ padding: 18, background: theme.surface,
                  border: `1px solid ${theme.border}`, borderRadius: theme.radius,
                  display: 'flex', flexWrap: 'wrap', gap: 14 }}>
      <Row label="PLUGIN" value={plugin} onChange={setPlugin} options={plugins} />
      <Row label="INPUT"  value={inputDevice} onChange={setInputDevice} options={inputs} />
      <Row label="OUTPUT" value={outputDevice} onChange={setOutputDevice} options={outputs} />
      <div style={{ width: '100%', display: 'flex', justifyContent: 'flex-end' }}>
        <button onClick={onRestart}
          style={{ fontFamily: theme.mono, fontSize: 10, letterSpacing: '0.12em',
                   fontWeight: 700, padding: '8px 14px', background: 'transparent',
                   border: `1px solid ${theme.border}`,
                   borderRadius: Math.max(theme.radius - 2, 2),
                   color: theme.textDim, cursor: 'pointer' }}>
          RESTART AUDIO
        </button>
      </div>
    </div>
  );
}

function ErrorBar({ theme, message, onClose }) {
  return (
    <div style={{ padding: '12px 14px', background: 'rgba(232, 132, 90, 0.08)',
                  border: '1px solid rgba(232, 132, 90, 0.4)',
                  borderRadius: theme.radius, color: '#f4b89e',
                  fontFamily: theme.mono, fontSize: 12,
                  display: 'flex', justifyContent: 'space-between', gap: 10 }}>
      <span>⚠ {message}</span>
      <button onClick={onClose} style={{ background: 'transparent', border: 'none',
              color: 'inherit', cursor: 'pointer', fontFamily: 'inherit' }}>✕</button>
    </div>
  );
}

function LoadingState({ theme }) {
  return (
    <div style={{ padding: '40px 8px', color: theme.textDim,
                  fontFamily: theme.mono, fontSize: 11, letterSpacing: '0.14em' }}>
      CONNECTING…
    </div>
  );
}

function EmptyState({ theme, anchorCount, onPick }) {
  return (
    <div style={{ padding: '24px 4px', display: 'flex',
                  flexDirection: 'column', gap: 14 }}>
      <div style={{ fontFamily: theme.mono, fontSize: 10, letterSpacing: '0.16em',
                    color: theme.textDim, fontWeight: 700 }}>TRY</div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {EXAMPLE_QUERIES.map(q => (
          <button key={q} onClick={() => onPick(q)}
            style={{ fontFamily: theme.display, fontSize: 13, padding: '8px 14px',
                     background: theme.card, border: `1px solid ${theme.border}`,
                     borderRadius: 999, color: theme.text, cursor: 'pointer',
                     transition: 'all 0.15s ease' }}
            onMouseEnter={(e) => { e.currentTarget.style.borderColor = theme.accent;
                                   e.currentTarget.style.color = theme.accent; }}
            onMouseLeave={(e) => { e.currentTarget.style.borderColor = theme.border;
                                   e.currentTarget.style.color = theme.text; }}>
            {q}
          </button>
        ))}
      </div>
      <div style={{ marginTop: 18, padding: 18, background: theme.accentSoft,
                    border: `1px dashed ${theme.accent}`, borderRadius: theme.radius,
                    fontSize: 12.5, color: theme.text, lineHeight: 1.55 }}>
        <div style={{ fontFamily: theme.mono, fontSize: 10, letterSpacing: '0.14em',
                      color: theme.accent, fontWeight: 700, marginBottom: 6 }}>
          HOW IT WORKS
        </div>
        Describe any tone in your own words. {anchorCount} factory-preset anchors are embedded;
        your query is matched by meaning, and the closest preset loads lossless (~170 params)
        into the plugin while your guitar streams through it.
      </div>
    </div>
  );
}

function SearchingState({ theme, query, anchorCount }) {
  return (
    <div style={{ padding: '12px 4px', display: 'flex', alignItems: 'center', gap: 14 }}>
      <div style={{ display: 'flex', gap: 3 }}>
        <span style={{ width: 4, height: 4, borderRadius: '50%', background: theme.accent,
                       animation: 'bar 0.9s ease-in-out infinite' }} />
        <span style={{ width: 4, height: 4, borderRadius: '50%', background: theme.accent,
                       animation: 'bar 0.9s ease-in-out 0.15s infinite' }} />
        <span style={{ width: 4, height: 4, borderRadius: '50%', background: theme.accent,
                       animation: 'bar 0.9s ease-in-out 0.3s infinite' }} />
      </div>
      <div style={{ fontFamily: theme.mono, fontSize: 11, color: theme.textDim,
                    letterSpacing: '0.08em' }}>
        EMBEDDING "{query}" · SCORING {anchorCount} ANCHORS…
      </div>
    </div>
  );
}

function ResultsList({ results, theme, applied, onApply, onBlend, anchorCount }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <div style={{ fontFamily: theme.mono, fontSize: 10, letterSpacing: '0.16em',
                      color: theme.textDim, fontWeight: 700 }}>
          TOP {results.length} · FROM {anchorCount} ANCHORS
        </div>
        <button onClick={onBlend}
          style={{ fontFamily: theme.mono, fontSize: 10, letterSpacing: '0.12em',
                   fontWeight: 700, padding: '6px 12px',
                   background: applied === '__blend__' ? theme.accentSoft : 'transparent',
                   border: `1px solid ${applied === '__blend__' ? theme.accent : theme.border}`,
                   borderRadius: Math.max(theme.radius - 2, 2),
                   color: applied === '__blend__' ? theme.accent : theme.textDim,
                   cursor: 'pointer' }}>
          ◇ BLEND ALL
        </button>
      </div>
      <div style={{ display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 10 }}>
        {results.map((p, i) => (
          <div key={p.id} className="match-enter" style={{ animationDelay: `${i * 60}ms` }}>
            <MatchCard preset={p} rank={i + 1} applied={applied} playing={true}
                       onApply={onApply} theme={theme} />
          </div>
        ))}
      </div>
    </div>
  );
}

function RefineSection({ theme, applied, appliedName, history, input, setInput, onRun }) {
  return (
    <div style={{ marginTop: 6, padding: 20, background: theme.surface,
                  border: `1px solid ${theme.border}`, borderRadius: theme.radius,
                  display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between',
                    alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontFamily: theme.mono, fontSize: 10, letterSpacing: '0.14em',
                        color: theme.accent, fontWeight: 700 }}>● NOW PLAYING</div>
          <div style={{ fontFamily: theme.display, fontSize: 16, fontWeight: 600,
                        marginTop: 4, letterSpacing: theme.displayTracking }}>
            {appliedName || (applied === '__blend__' ? 'Blend of top matches' : 'Applied preset')}
          </div>
        </div>
        <div style={{ fontFamily: theme.mono, fontSize: 10, letterSpacing: '0.1em',
                      color: theme.textDim }}>REFINE · DELTA COMMANDS</div>
      </div>

      {history.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {history.map((h, i) => (
            <div key={i} style={{ fontFamily: theme.mono, fontSize: 11,
                                  padding: '5px 10px', background: theme.accentSoft,
                                  color: theme.accent,
                                  borderRadius: Math.max(theme.radius - 4, 2),
                                  fontWeight: 600 }}>
              ↳ {h.text}
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
        <input value={input} onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') onRun(); }}
          placeholder="brighter, more gain, less fizzy…"
          style={{ flex: 1, padding: '11px 14px', background: theme.card,
                   border: `1px solid ${theme.border}`,
                   borderRadius: Math.max(theme.radius - 2, 2),
                   color: theme.text, fontFamily: theme.display, fontSize: 14,
                   outline: 'none' }} />
        <button onClick={() => onRun()}
          style={{ fontFamily: theme.mono, fontSize: 11, letterSpacing: '0.14em',
                   fontWeight: 700, padding: '11px 16px',
                   background: input.trim() ? theme.accent : 'transparent',
                   color: input.trim() ? theme.bg : theme.textDim,
                   border: `1px solid ${input.trim() ? theme.accent : theme.border}`,
                   borderRadius: Math.max(theme.radius - 2, 2),
                   cursor: input.trim() ? 'pointer' : 'default' }}>
          APPLY ⏎
        </button>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {REFINE_CHIPS.map(c => (
          <button key={c} onClick={() => onRun(c)}
            style={{ fontFamily: theme.mono, fontSize: 11, fontWeight: 600,
                     padding: '6px 11px', background: 'transparent',
                     border: `1px solid ${theme.border}`, borderRadius: 999,
                     color: theme.textDim, cursor: 'pointer',
                     transition: 'all 0.15s ease' }}
            onMouseEnter={(e) => { e.currentTarget.style.borderColor = theme.accent;
                                   e.currentTarget.style.color = theme.accent; }}
            onMouseLeave={(e) => { e.currentTarget.style.borderColor = theme.border;
                                   e.currentTarget.style.color = theme.textDim; }}>
            {c}
          </button>
        ))}
      </div>
    </div>
  );
}

function NoPluginState({ theme, onRetry }) {
  return (
    <div style={{ padding: '48px 24px', textAlign: 'center', background: theme.surface,
                  border: `1px dashed ${theme.border}`, borderRadius: theme.radius,
                  display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14 }}>
      <div style={{ width: 44, height: 44, borderRadius: '50%',
                    background: theme.accentSoft,
                    display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none"
             stroke={theme.accent} strokeWidth="1.8">
          <path d="M10 2v6M10 18v-2M4.5 4.5l4 4M15.5 15.5l-4-4"/>
          <circle cx="10" cy="10" r="8"/>
        </svg>
      </div>
      <div style={{ fontFamily: theme.display, fontSize: 17, fontWeight: 600 }}>
        No Neural DSP plugin found
      </div>
      <div style={{ fontSize: 13, color: theme.textDim, maxWidth: 420, lineHeight: 1.5 }}>
        Install an Archetype VST3 at{' '}
        <code style={{ fontFamily: theme.mono, color: theme.text, background: theme.card,
                       padding: '1px 6px', borderRadius: 3 }}>
          /Library/Audio/Plug-Ins/VST3/
        </code>{' '}— Tim Henson X or Cory Wong X supported.
      </div>
      <button onClick={onRetry}
        style={{ fontFamily: theme.mono, fontSize: 11, letterSpacing: '0.14em',
                 fontWeight: 700, padding: '10px 16px', marginTop: 6,
                 background: theme.accent, color: theme.bg, border: 'none',
                 borderRadius: Math.max(theme.radius - 2, 2), cursor: 'pointer' }}>
        CHECK AGAIN
      </button>
    </div>
  );
}

function BuildingState({ theme, anchorCount }) {
  return (
    <div style={{ padding: 28, background: theme.surface,
                  border: `1px solid ${theme.border}`, borderRadius: theme.radius,
                  display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div>
        <div style={{ fontFamily: theme.mono, fontSize: 10, letterSpacing: '0.14em',
                      color: theme.accent, fontWeight: 700 }}>
          FIRST-RUN · ANCHOR DATABASE MISSING
        </div>
        <div style={{ fontFamily: theme.display, fontSize: 18, fontWeight: 600,
                      marginTop: 8, letterSpacing: theme.displayTracking }}>
          Build the anchor database to start
        </div>
        <div style={{ fontSize: 12.5, color: theme.textDim, marginTop: 6, lineHeight: 1.5 }}>
          Each preset is loaded into the plugin, measured across ~170 params, then
          described from what we observed. Runs once · ~8 min.
        </div>
      </div>
      <div style={{ fontFamily: theme.mono, fontSize: 11, color: theme.textDim,
                    background: theme.card, padding: '12px 14px',
                    borderRadius: Math.max(theme.radius - 4, 2),
                    border: `1px solid ${theme.border}`, lineHeight: 1.6 }}>
        <div style={{ color: theme.text }}>In a terminal, run:</div>
        <div style={{ color: theme.accent, marginTop: 6 }}>
          uv run python scripts/build_anchor_db.py
        </div>
        <div style={{ marginTop: 6 }}>
          This page checks every 3 seconds — it will refresh automatically when done.
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { ToneController });

// Mount
const rootEl = document.getElementById('root');
if (rootEl) {
  ReactDOM.createRoot(rootEl).render(React.createElement(ToneController));
}
