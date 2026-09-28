import { avatarGradient, codename, shortAddr } from "../utils/walletName.js";

// A wallet as a gradient dot and its made-up codename ("Cobalt Heron"); the full address is in
// the hover title, and `addr` adds the short address after the name.
export default function WalletTag({ address, name, size = 14, addr = false, className = "" }) {
  if (!address) return null;
  const label = name || codename(address);
  return (
    <span className={`wtag${className ? ` ${className}` : ""}`} title={`${label}\n${address}`}>
      <span className="wtag-av" aria-hidden="true" style={{ width: size, height: size, background: avatarGradient(address) }} />
      <span className="wtag-name">{label}</span>
      {addr && <span className="wtag-addr">{shortAddr(address)}</span>}
    </span>
  );
}
