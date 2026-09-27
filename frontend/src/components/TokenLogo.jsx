import { useState } from 'react';
import logos from '../data/tokenLogos.json';
import { getBaseSymbol, T } from '../theme.js';

// A 1px ring keeps dark logos (WLD, NOT) visible on the dark canvas.
const RING = '0 0 0 1px var(--t-overlay10)';

export default function TokenLogo({ symbol, size = 24 }) {
  const [failedSource, setFailedSource] = useState(null);
  const src = logos[symbol]?.src;
  const style = { width: size, height: size, flexShrink: 0, verticalAlign: 'middle', objectFit: 'contain', boxShadow: RING };
  if (src && failedSource !== src) return <img src={src} alt="" width={size} height={size}
    loading="lazy" style={{ ...style, borderRadius: '50%' }} onError={() => setFailedSource(src)} />;
  return <span aria-hidden="true" style={{ ...style, display: 'inline-flex', alignItems: 'center',
    justifyContent: 'center', background: T.overlay04, color: T.text3, borderRadius: 6,
    fontFamily: T.mono, fontSize: Math.max(11, size * .38), fontWeight: 700, letterSpacing: 0 }}>
    {getBaseSymbol(symbol || '?').slice(0, 2)}
  </span>;
}
