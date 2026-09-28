import { useId } from "react";
import { T, themeToken } from "../theme.js";
import { useTheme } from "../ThemeContext";
import { LETTERING_VIEWBOX, LETTERING_TRANSFORM, LETTERING_PATHS } from "./brandLettering.js";

// "#c2ded6 0%, ..." inside a token's linear-gradient() -> [[colour, offset], ...]
const stops = gradient => [...String(gradient || "").matchAll(/(#[0-9a-f]{3,8}|rgba?\([^)]*\))\s+([\d.]+)%/gi)].map(m => [m[1], `${m[2]}%`]);

// The header's wordmark: the lettering filled with the brand metal (metalType bands, multiplied
// by the metalTypeHorizon light), pale aluminium in dark and gunmetal in light.
function MetalWordmark({ width, height }) {
  const { mode } = useTheme();
  const id = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const [x, y, w, h] = LETTERING_VIEWBOX.split(" ");
  const box = { x, y, width: w, height: h };
  return (
    <svg className="header-wordmark" role="img" aria-label="reflex" viewBox={LETTERING_VIEWBOX} width={width} height={height}>
      <defs>
        <linearGradient id={`${id}b`} x1="0" x2="1" y1="0" y2="0">
          {stops(themeToken(mode, "metalType")).map(([c, o]) => <stop key={o} offset={o} stopColor={c} />)}
        </linearGradient>
        <linearGradient id={`${id}h`} x1="0" x2="0" y1="0" y2="1">
          {stops(themeToken(mode, "metalTypeHorizon")).map(([c, o]) => <stop key={o} offset={o} stopColor={c} />)}
        </linearGradient>
        <mask id={`${id}m`} maskUnits="userSpaceOnUse" {...box}>
          <g transform={LETTERING_TRANSFORM} fill="#fff">
            {LETTERING_PATHS.map(([dx, d]) => <path key={dx} transform={`translate(${dx} 0)`} d={d} />)}
          </g>
        </mask>
      </defs>
      <g mask={`url(#${id}m)`} style={{ isolation: "isolate" }}>
        <rect className="wordmark-metal" {...box} fill={`url(#${id}b)`} />
        <rect className="wordmark-metal" {...box} fill={`url(#${id}h)`} style={{ mixBlendMode: "multiply" }} />
      </g>
    </svg>
  );
}

export default function ReflexBrand({ compact = false, onClick, metal = false, className }) {
  const mark = <img className={metal ? "brand-mark" : undefined} src="/brand/reflex-ribbon-transparent.svg" alt="" width={compact ? 30 : 38} height={compact ? 30 : 38} />;
  const content = <>{mark}{metal
    ? <MetalWordmark width={compact ? 82 : 96} height={compact ? 25 : 29} />
    : <img className="terminal-wordmark" src="/brand/reflex-lettering-clean.svg" alt="reflex" width={compact ? 82 : 96} height={compact ? 25 : 29} />}</>;
  const style = {display:"inline-flex", alignItems:"center", gap:10, flexShrink:0, background:"none", border:0, padding:0, fontFamily:"var(--font-display), sans-serif"};
  return onClick ? <button type="button" className={className} aria-label="Reflex scanner" onClick={onClick} style={{...style,cursor:"pointer"}}>{content}</button> : <div aria-label="Reflex" style={style}>{content}</div>;
}
