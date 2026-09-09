import { T } from "../theme.js";
export default function ReflexBrand({ compact = false, onClick }) {
  const content = <><img src="/brand/reflex-ribbon-transparent.svg" alt="" width={compact ? 30 : 38} height={compact ? 30 : 38} /><img className="terminal-wordmark" src="/brand/reflex-lettering-clean.svg" alt="reflex" width={compact ? 82 : 96} height={compact ? 25 : 29} /></>;
  const style = {display:"inline-flex", alignItems:"center", gap:10, flexShrink:0, background:"none", border:0, padding:0, fontFamily:"var(--font-display), sans-serif"};
  return onClick ? <button type="button" aria-label="Reflex scanner" onClick={onClick} style={{...style,cursor:"pointer"}}>{content}</button> : <div aria-label="Reflex" style={style}>{content}</div>;
}
