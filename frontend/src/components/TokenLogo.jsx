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
// Artwork that vanishes on one theme's canvas, measured from the same SVGs (luminance of the
// opaque pixels and how much of the circle they fill). DARK_ART: near-black marks on a
// transparent background (NEAR, ETH, XRP, WLD ...), backed by a light disc in dark theme.
// LIGHT_ART: white or pale marks on transparent (HYPE, XPL ...), backed by a dark disc in light
// theme. DARK_DISC: a full near-black disc (FARTCOIN), outlined more strongly in dark theme.
// The artwork itself is never changed.
const DARK_ART = new Set([
  '4940286b73b2adfe', 'da698c1f88dfdfe0', '0196e1bbe11b6110', '1103c7a03e67c3ef', '1186309d94304915', 'b00c4723b2cb24c3',
  '02419b220e441733', '6b7ba2fef66324ee', 'ee512442a4257951', '55c3afd659571ec1', '8ef1b7dc4a4b80a8', '7070b94594f959e6',
]); // AR BIGTIME CFX DYM ETH GALA MEGA NEAR ONDO WLD XLM XRP
const LIGHT_ART = new Set([
  '4114ff162070e7f0', '9f52e8862e100903', '4ef1f539cdd3472f', 'b98fec0860869712', 'c66460b6de1635ad', '66f26beb272db287',
  '24ef02b06b59ffbf', 'bdfd701af097640d', 'eca991175c53b0cd', '0531f02d8f9fecbf', '7b5ec3788b12796c',
]); // ACE APEX HYPE IO REZ RUNE S SAGA SOPH STABLE XPL
const DARK_DISC = new Set(['1db8c284aaa50a2f']); // FARTCOIN
const logoId = src => src.slice(src.lastIndexOf('/') + 1).replace(/\.svg$/, '');
const backing = id => (DARK_ART.has(id) ? ' token-logo-dk' : LIGHT_ART.has(id) ? ' token-logo-lt' : DARK_DISC.has(id) ? ' token-logo-dkdisc' : '');

// fallback: what a coin with no artwork gets. 'monogram' (default) draws its first two letters;
// 'ring' reserves the slot with an empty ring, for places where the ticker is printed right beside
// it (the monogram would only repeat it); 'none' renders nothing.
export default function TokenLogo({ symbol, size = 24, fallback = 'monogram' }) {
  const [failedSource, setFailedSource] = useState(null);
  const src = logos[symbol]?.src;
  const box = { width: size, height: size, flexShrink: 0, verticalAlign: 'middle' };
  if (src && failedSource !== src) {
    const onError = () => setFailedSource(src);
    if (SQUARE.has(logoId(src))) return <img src={src} alt="" width={size} height={size}
      loading="lazy" style={{ ...box, objectFit: 'contain', boxShadow: RING }} onError={onError} />;
    return <span className={`token-logo${backing(logoId(src))}`} style={{ ...box, display: 'inline-flex', borderRadius: '50%', boxShadow: RING }}>
      <img src={src} alt="" width={size} height={size} loading="lazy"
        style={{ display: 'block', width: size, height: size, objectFit: 'contain' }} onError={onError} />
    </span>;
  }
  if (fallback === 'none') return null;
  if (fallback === 'ring') return <span aria-hidden="true" style={{ ...box, display: 'inline-block', borderRadius: '50%', boxShadow: RING, background: T.overlay04 }} />;
  return <span aria-hidden="true" style={{ ...box, objectFit: 'contain', boxShadow: RING, display: 'inline-flex', alignItems: 'center',
    justifyContent: 'center', background: T.overlay04, color: T.text3, borderRadius: 6,
    fontFamily: T.mono, fontSize: Math.max(11, size * .38), fontWeight: 700, letterSpacing: 0 }}>
    {getBaseSymbol(symbol || '?').slice(0, 2)}
  </span>;
}
