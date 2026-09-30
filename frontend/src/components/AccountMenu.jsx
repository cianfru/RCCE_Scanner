import { useEffect, useRef, useState } from "react";
import { signIn, signOut, telegramLink, telegramPrefs, telegramUnlink, useAccount } from "../account.js";
import { LOCK_TITLE, lockHelp, nextQuiet, quietText, shortAddress } from "../utils/account.js";
import HelpTip from "./HelpTip.jsx";

// The header's wallet entry (VITE_ACCOUNTS): "Sign in", or the short address opening a small
// panel with the tier, the Telegram link and sign-out. The login screen is not involved.
export default function AccountMenu() {
  const me = useAccount();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [link, setLink] = useState(null);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const close = e => { if (!ref.current?.contains(e.target)) setOpen(false); };
    const esc = e => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("pointerdown", close); document.removeEventListener("keydown", esc); };
  }, [open]);

  if (!me || !me.accounts) return null;

  const run = async fn => {
    if (busy) return;
    setBusy(true); setMsg("");
    try { await fn(); } catch (e) { setMsg(e?.code === 4001 ? "Cancelled in the wallet." : e?.message || "Something went wrong."); }
    finally { setBusy(false); }
  };

  if (!me.address) {
    return (
      <span className="acct" ref={ref}>
        <button type="button" className="header-theme" disabled={busy} onClick={() => run(signIn)}
          title="Sign in with a wallet: signs a message, no transaction">{busy ? "Signing…" : "Sign in"}</button>
        {msg && <span className="acct-msg" role="status">{msg}</span>}
      </span>
    );
  }

  const tg = me.telegram || {};
  const holder = !me.tiers || me.tier === "holder";
  return (
    <span className="acct" ref={ref}>
      <button type="button" className="header-theme" aria-expanded={open} onClick={() => setOpen(v => !v)}
        title={me.address}>{shortAddress(me.address)}</button>
      {open && (
        <div className="acct-panel" role="dialog" aria-label="Account">
          <div className="acct-row">
            <span className="acct-dim">{me.tiers ? (holder ? "Holder" : "Free") : "Signed in"}</span>
            {me.tiers && !holder && <HelpTip title={LOCK_TITLE} width={300} label="About access">{lockHelp(me).map(l => <p key={l}>{l}</p>)}</HelpTip>}
          </div>
          {holder && !me.owner && (
            <div className="acct-row">
              <span>Telegram</span>
              {tg.status === "ready"
                ? <button type="button" className="te-link" onClick={() => run(telegramUnlink)}>Unlink</button>
                : tg.status === "off" ? <span className="acct-dim">not running</span>
                : <button type="button" className="te-link" onClick={() => run(async () => setLink(await telegramLink()))}>Link</button>}
            </div>
          )}
          {link && tg.status !== "ready" && (
            <p className="acct-code">
              Send <b>/start {link.code}</b> to the bot{link.url ? <> · <a href={link.url} target="_blank" rel="noreferrer">open</a></> : null}
            </p>
          )}
          {holder && !me.owner && tg.status === "ready" && <>
            <div className="acct-row">
              <span>Quiet hours</span>
              <button type="button" className="te-link" onClick={() => run(() => telegramPrefs({ quiet: nextQuiet(tg.quiet) }))}>{quietText(tg.quiet)}</button>
            </div>
            <div className="acct-row">
              <span>Daily brief</span>
              <button type="button" className="te-link" onClick={() => run(() => telegramPrefs({ brief: !tg.brief }))}>{tg.brief ? "on" : "off"}</button>
            </div>
          </>}
          <div className="acct-row">
            <button type="button" className="te-link" onClick={() => run(async () => { await signOut(); setOpen(false); setLink(null); })}>Sign out</button>
          </div>
          {msg && <p className="acct-msg" role="status">{msg}</p>}
        </div>
      )}
    </span>
  );
}
