import { useId } from "react";
import { AVATAR_VIEW, avatarShapes, avatarSpec } from "../utils/walletAvatar.js";
import { codename, shortAddr } from "../utils/walletName.js";

// The wallet's face, drawn from its address.
export function WalletAvatar({ address, size = 20 }) {
  const clip = useId();
  const s = avatarSpec(address);
  const sh = avatarShapes(s);
  const V = AVATAR_VIEW;
  const stroke = { fill: "none", stroke: s.ink, strokeWidth: 2, strokeLinecap: "round" };
  const mark = (e, i) => {
    const { tag, fill, ...a } = e;
    const paint = tag === "circle" || fill ? { fill: s.ink } : stroke;
    if (tag === "circle") return <circle key={i} {...a} {...paint} />;
    if (tag === "line") return <line key={i} {...a} {...paint} />;
    return <path key={i} {...a} {...paint} />;
  };
  return (
    <svg className="wtag-av" width={size} height={size} viewBox={`0 0 ${V} ${V}`} aria-hidden="true" focusable="false">
      <defs><clipPath id={clip}><circle cx={V / 2} cy={V / 2} r={V / 2} /></clipPath></defs>
      <g clipPath={`url(#${clip})`}>
        <rect width={V} height={V} fill={s.bg} />
        <rect {...sh.body} fill={s.body} />
        <g transform={sh.faceTransform}>{sh.eyes.map(mark)}{mark(sh.mouth, "m")}</g>
      </g>
    </svg>
  );
}

// A wallet as its avatar and made-up codename ("Cobalt Heron"); the full address is in the
// hover title. addr: the short address after the name; sub: the short address under it.
export default function WalletTag({ address, name, size = 20, addr = false, sub = false, className = "" }) {
  if (!address) return null;
  const label = name || codename(address);
  return (
    <span className={`wtag${sub ? " wtag-stack" : ""}${className ? ` ${className}` : ""}`} title={`${label}\n${address}`}>
      <WalletAvatar address={address} size={size} />
      {sub
        ? <span className="wtag-text"><span className="wtag-name">{label}</span><span className="wtag-addr">{shortAddr(address)}</span></span>
        : <span className="wtag-name">{label}</span>}
      {addr && !sub && <span className="wtag-addr">{shortAddr(address)}</span>}
    </span>
  );
}
