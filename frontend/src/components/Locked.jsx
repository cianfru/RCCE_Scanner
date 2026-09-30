import HelpTip from "./HelpTip.jsx";
import { useAccount } from "../account.js";
import { LOCK_TITLE, lockHelp } from "../utils/account.js";

// A holder feature seen by the free tier (access tiers on): one quiet line, the way in behind (i).
export default function Locked({ what }) {
  const me = useAccount();
  return (
    <p className="acct-locked">
      <span>{what} · token holders</span>
      <HelpTip title={LOCK_TITLE} width={300} label="How to get access">
        {lockHelp(me).map(l => <p key={l}>{l}</p>)}
      </HelpTip>
    </p>
  );
}
