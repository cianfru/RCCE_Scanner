import { T } from "../theme.js";
export default function ReflexBrand({ compact = false, onClick }) {
  const content = <><img src="/brand/reflex-ribbon-transparent.svg" alt="" width={compact ? 30 : 38} height={compact ? 30 : 38} /><span style={{fontSize: compact ? 24 : 28, fontWeight:600, letterSpacing:"-1.3px", color:T.text1}}>reflex</span></>;
  const style = {display:"inline-flex", alignItems:"center", gap:10, flexShrink:0, background:"none", border:0, padding:0, fontFamily:T.font};
  return onClick ? <button type="button" aria-label="Reflex scanner" onClick={onClick} style={{...style,cursor:"pointer"}}>{content}</button> : <div aria-label="Reflex" style={style}>{content}</div>;
}
