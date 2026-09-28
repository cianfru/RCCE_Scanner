import { useState } from 'react';
import logos from '../data/tokenLogos.json';
import { getBaseSymbol, T } from '../theme.js';

// A 1px ring keeps dark logos (WLD, NOT) visible on the dark canvas. It never crops the artwork:
// round logos get a round ring on a wrapper; square artwork gets the ring on its own box.
const RING = '0 0 0 1px var(--t-overlay10)';
// Logos drawn as squares or rounded squares (opaque corners, or mostly outside the inscribed
// circle), measured from the cached SVGs in public/token-logos. A logo missing from this list
// (e.g. after a refresh) gets the round ring, which still crops nothing.
const SQUARE = new Set([
  'e9f20d802cb782af', // BANANA
  '6077aac9fc506ea8', // DYDX
  'c06b67e09cb1ddad', // EIGEN
  'ea4c3b8070d65592', // FET
  '3f4deef0a498bf7c', // FOGO
  '9d3ab8dd58feb2a3', // GRASS
  'ef8775279f62e71d', // LINEA
  '12e1514c19f70e8d', // MINA
  '81a440ccc59c55bd', // NOT
  '62e645b902fc7edc', // SUPER
  'f2b67eef1ef2247e', // TAO
  '795389b642657c33', // TIA
  '98610772c13a2a3d', // ZRO
]);
const logoId = src => src.slice(src.lastIndexOf('/') + 1).replace(/\.svg$/, '');

export default function TokenLogo({ symbol, size = 24 }) {
  const [failedSource, setFailedSource] = useState(null);
  const src = logos[symbol]?.src;
  const box = { width: size, height: size, flexShrink: 0, verticalAlign: 'middle' };
  if (src && failedSource !== src) {
    const onError = () => setFailedSource(src);
    if (SQUARE.has(logoId(src))) return <img src={src} alt="" width={size} height={size}
      loading="lazy" style={{ ...box, objectFit: 'contain', boxShadow: RING }} onError={onError} />;
    return <span className="token-logo" style={{ ...box, display: 'inline-flex', borderRadius: '50%', boxShadow: RING }}>
      <img src={src} alt="" width={size} height={size} loading="lazy"
        style={{ display: 'block', width: size, height: size, objectFit: 'contain' }} onError={onError} />
    </span>;
  }
  return <span aria-hidden="true" style={{ ...box, objectFit: 'contain', boxShadow: RING, display: 'inline-flex', alignItems: 'center',
    justifyContent: 'center', background: T.overlay04, color: T.text3, borderRadius: 6,
    fontFamily: T.mono, fontSize: Math.max(11, size * .38), fontWeight: 700, letterSpacing: 0 }}>
    {getBaseSymbol(symbol || '?').slice(0, 2)}
  </span>;
}
