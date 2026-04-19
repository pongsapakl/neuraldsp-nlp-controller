// Tone Controller — primitive components and theme.
// Container (state/routing/API) lives in shell.jsx.

const { useState, useEffect, useRef } = React;

const REFINE_CHIPS = [
  'brighter', 'darker', 'warmer',
  'more gain', 'less gain', 'less fizzy',
  'add delay', 'more reverb', 'tighter low end',
];

const EXAMPLE_QUERIES = [
  'warm blues crunch',
  'ambient shimmer',
  '80s chorus clean',
  'jazzy room tone',
  'spaghetti western lead',
];

// Score → confidence band. Thresholds from user's empirical feel with MiniLM.
function confidenceLabel(score) {
  if (score >= 0.70) return { label: 'STRONG MATCH', tier: 3 };
  if (score >= 0.40) return { label: 'CLOSE MATCH',  tier: 2 };
  return                     { label: 'LOOSE',        tier: 1 };
}

// 6 vertical bars: GAIN BASS MID TREB VERB DLY.
function ToneBars({ chars, theme }) {
  const entries = [
    ['GAIN', chars.gain], ['BASS', chars.bass], ['MID',  chars.mid],
    ['TREB', chars.treb], ['VERB', chars.verb], ['DLY',  chars.dly],
  ];
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 6, alignItems: 'end' }}>
      {entries.map(([label, v]) => (
        <div key={label} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5 }}>
          <div style={{ height: 42, width: '100%', display: 'flex', alignItems: 'flex-end',
                        background: theme.barTrack, borderRadius: 2, overflow: 'hidden' }}>
            <div style={{ width: '100%', height: `${Math.max((v ?? 0) * 100, 3)}%`,
                          background: (v ?? 0) > 0.02 ? theme.accent : theme.borderStrong,
                          transition: 'height 0.35s cubic-bezier(.2,.8,.2,1)' }} />
          </div>
          <div style={{ fontFamily: theme.mono, fontSize: 8.5, letterSpacing: '0.1em',
                        color: theme.textDim, fontWeight: 600 }}>{label}</div>
        </div>
      ))}
    </div>
  );
}

// Streaming indicator: pulsing dot + label.
function LiveDot({ theme, active }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ position: 'relative', width: 10, height: 10 }}>
        <div style={{ position: 'absolute', inset: 0, borderRadius: '50%',
                      background: active ? theme.accent : theme.textDim,
                      boxShadow: active ? `0 0 8px ${theme.accent}` : 'none' }} />
        {active && (
          <div style={{ position: 'absolute', inset: -3, borderRadius: '50%',
                        border: `1px solid ${theme.accent}`,
                        animation: 'livePulse 1.6s ease-out infinite' }} />
        )}
      </div>
      <span style={{ fontFamily: theme.mono, fontSize: 10, letterSpacing: '0.14em',
                     color: active ? theme.text : theme.textDim, fontWeight: 600 }}>
        {active ? 'STREAMING' : 'IDLE'}
      </span>
    </div>
  );
}

function MatchCard({ preset, rank, applied, playing, onApply, theme }) {
  const [hover, setHover] = useState(false);
  const isActive = applied === preset.id;
  const conf = confidenceLabel(preset.score);

  return (
    <div
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onClick={() => onApply(preset.id)}
      style={{
        position: 'relative', padding: 14,
        background: isActive ? theme.cardActive : (hover ? theme.cardHover : theme.card),
        border: `1px solid ${isActive ? theme.accent : theme.border}`,
        borderRadius: theme.radius, cursor: 'pointer', transition: 'all 0.15s ease',
        display: 'flex', flexDirection: 'column', gap: 11, minHeight: 190,
        boxShadow: isActive ? `0 0 0 1px ${theme.accent}, 0 8px 24px -10px ${theme.accent}` : 'none',
      }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <div style={{ fontFamily: theme.mono, fontSize: 10, fontWeight: 700,
                      color: isActive ? theme.accent : theme.textDim, letterSpacing: '0.08em' }}>
          {String(rank).padStart(2, '0')}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ display: 'flex', gap: 2 }}>
            {[0, 1, 2, 3].map(i => (
              <span key={i} style={{ width: 4, height: 4, borderRadius: '50%',
                                     background: i <= conf.tier ? theme.accent : theme.borderStrong }} />
            ))}
          </div>
          <span style={{ fontFamily: theme.mono, fontSize: 9, fontWeight: 700,
                         letterSpacing: '0.1em',
                         color: conf.tier >= 2 ? theme.accent : theme.textDim }}>
            {conf.label}
          </span>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, minHeight: 42 }}>
        <div style={{ flex: 1, minWidth: 0, fontFamily: theme.display, fontSize: 15, fontWeight: 600,
                      color: theme.text, letterSpacing: theme.displayTracking, lineHeight: 1.22,
                      wordBreak: 'break-word' }}>
          {preset.name}
        </div>
        {isActive && playing && (
          <div style={{ display: 'flex', gap: 2, alignItems: 'flex-end', height: 13,
                        flexShrink: 0, paddingTop: 4 }}>
            <span style={{ width: 2, height: '100%', background: theme.accent,
                           animation: 'bar 0.6s ease-in-out infinite' }} />
            <span style={{ width: 2, height: '100%', background: theme.accent,
                           animation: 'bar 0.6s ease-in-out 0.15s infinite' }} />
            <span style={{ width: 2, height: '100%', background: theme.accent,
                           animation: 'bar 0.6s ease-in-out 0.3s infinite' }} />
          </div>
        )}
      </div>

      <div style={{ fontSize: 11.5, color: theme.textDim, lineHeight: 1.45, flex: 1 }}>
        {preset.desc}
      </div>

      <ToneBars chars={preset.chars || {}} theme={theme} />

      <div style={{ fontFamily: theme.mono, fontSize: 9, color: theme.textDim,
                    letterSpacing: '0.12em', textTransform: 'uppercase',
                    paddingTop: 8, borderTop: `1px solid ${theme.border}`,
                    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {preset.plugin}
      </div>
    </div>
  );
}

// Indie theme — the only one we ship.
function getTheme() {
  return {
    bg: '#0c1420', bgAlt: '#101a2a', surface: '#132033',
    card: '#16263c', cardHover: '#1b2e48', cardActive: '#1f3553',
    border: '#1f3150', borderStrong: '#2b4267',
    text: '#e2ecf8', textDim: '#7e96b4', textFaint: '#4a5d7a',
    accent: 'oklch(0.80 0.12 230)',
    accentSoft: 'oklch(0.80 0.12 230 / 0.14)',
    barTrack: '#1a2a40',
    display: "'Inter Tight', -apple-system, sans-serif",
    displayTracking: '-0.01em',
    mono: "'JetBrains Mono', ui-monospace, monospace",
    radius: 14,
    ring: '0 0 0 3px oklch(0.80 0.12 230 / 0.22)',
  };
}

function SearchInput({ value, onChange, onSubmit, theme, disabled }) {
  const [focused, setFocused] = useState(false);
  const inputRef = useRef(null);
  useEffect(() => { inputRef.current?.focus(); }, []);
  return (
    <div style={{
      position: 'relative', display: 'flex', alignItems: 'center', gap: 12,
      padding: '14px 18px', background: theme.surface,
      border: `1px solid ${focused ? theme.accent : theme.border}`,
      borderRadius: theme.radius, transition: 'all 0.15s ease',
      boxShadow: focused ? theme.ring : 'none',
    }}>
      <div style={{ fontFamily: theme.mono, fontSize: 10, fontWeight: 700,
                    letterSpacing: '0.14em', color: focused ? theme.accent : theme.textDim }}>
        TONE
      </div>
      <div style={{ width: 1, height: 18, background: theme.border }} />
      <input
        ref={inputRef} value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        onKeyDown={(e) => { if (e.key === 'Enter') onSubmit(); }}
        placeholder="Describe a tone — warm blues crunch, ambient shimmer…"
        disabled={disabled}
        style={{ flex: 1, background: 'transparent', border: 'none', outline: 'none',
                 color: theme.text, fontFamily: theme.display, fontSize: 16,
                 letterSpacing: theme.displayTracking }} />
      <button
        onClick={onSubmit}
        style={{ fontFamily: theme.mono, fontSize: 11, fontWeight: 700,
                 letterSpacing: '0.14em', padding: '7px 12px',
                 background: value.trim() ? theme.accent : 'transparent',
                 color: value.trim() ? theme.bg : theme.textDim,
                 border: `1px solid ${value.trim() ? theme.accent : theme.border}`,
                 borderRadius: Math.max(theme.radius - 4, 2),
                 cursor: value.trim() ? 'pointer' : 'default',
                 transition: 'all 0.15s ease' }}>
        SEARCH ⏎
      </button>
    </div>
  );
}

Object.assign(window, { REFINE_CHIPS, EXAMPLE_QUERIES, confidenceLabel,
                        getTheme, MatchCard, ToneBars, LiveDot, SearchInput });
