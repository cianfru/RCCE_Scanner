// The navigation's one icon set: 16px line glyphs on a 16x16 grid, stroke 1.5, currentColor.
// Used by the header tabs, the phone tab bar and the More drawer. No lucide icons in navigation.
const S = { stroke: "currentColor", strokeWidth: 1.5 };

const GLYPHS = {
  "1d": <>
    <path d="M2 12L5 7L8 9L14 3" {...S} strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M2 14h12" {...S} strokeLinecap="round"/>
  </>,
  radar: <>
    <circle cx="8" cy="8" r="6" {...S}/>
    <circle cx="8" cy="8" r="2.5" {...S}/>
    <path d="M8 8L12.2 3.8" {...S} strokeLinecap="round"/>
    <circle cx="11" cy="5" r="1" fill="currentColor"/>
  </>,
  chat: <path d="M3 3h10a1 1 0 011 1v6a1 1 0 01-1 1H6l-3 3V4a1 1 0 011-1z" {...S} strokeLinejoin="round"/>,
  signals: <path d="M3 13V8M6 13V5M9 13V7M12 13V3" {...S} strokeLinecap="round"/>,
  hyperlens: <>
    <circle cx="8" cy="8" r="5" {...S}/>
    <circle cx="8" cy="8" r="2" {...S}/>
    <path d="M12 4l2-2M4 12l-2 2" {...S} strokeLinecap="round"/>
  </>,
  backtest: <>
    <rect x="2" y="2" width="5" height="5" rx="1" {...S}/>
    <rect x="9" y="2" width="5" height="5" rx="1" {...S}/>
    <rect x="2" y="9" width="5" height="5" rx="1" {...S}/>
    <rect x="9" y="9" width="5" height="5" rx="1" {...S}/>
  </>,
  executor: <path d="M5 2l8 6-8 6V2z" {...S} strokeLinejoin="round"/>,
  trading: <path d="M2 8h3l2-5 2 10 2-5h3" {...S} strokeLinecap="round" strokeLinejoin="round"/>,
  tradfi: <>
    <rect x="2" y="6" width="3" height="7" rx="0.5" {...S}/>
    <rect x="6.5" y="3" width="3" height="10" rx="0.5" {...S}/>
    <rect x="11" y="5" width="3" height="8" rx="0.5" {...S}/>
  </>,
  analytics: <>
    <path d="M2 13h12" {...S} strokeLinecap="round"/>
    <path d="M3 10v3M6 7v6M9 5v8M12 3v10" {...S} strokeLinecap="round"/>
  </>,
  settings: <>
    <path d="M2 4h12M2 8h12M2 12h12" {...S} strokeLinecap="round"/>
    <circle cx="5" cy="4" r="1.75" fill="currentColor"/>
    <circle cx="10" cy="8" r="1.75" fill="currentColor"/>
    <circle cx="7" cy="12" r="1.75" fill="currentColor"/>
  </>,
};

// Aliases: the main tabs use the existing glyphs under their new names.
const ALIAS = { scanner: "1d", "4h": "1d", traders: "hyperlens", portfolio: "trading" };

export function NavIcon({ name, size = 16 }) {
  const glyph = GLYPHS[ALIAS[name] || name];
  if (!glyph) return null;
  return <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-hidden="true" focusable="false">{glyph}</svg>;
}

export const NAV_ICONS = Object.fromEntries(Object.keys(GLYPHS).map(k => [k, <NavIcon key={k} name={k} />]));
