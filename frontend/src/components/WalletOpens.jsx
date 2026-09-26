import HelpTip from "./HelpTip.jsx";
import { col } from "../theme.js";
import { SIDE_COLOR, fmtPx, fmtWhen } from "../utils/traderFormat.js";

// New positions seen by the wallet sweep on one coin, and profitable-trader convergences.
export default function WalletOpens({ opens }) {
  const list = opens.opens || [];
  const prof = list.filter(o => o.cohort === "profitable").length;
  const convs = opens.convergences || [];
  return (
    <div className="te wo">
      <div>
        <strong>New positions in {opens.symbol}</strong>
        {" · "}{list.length ? `${prof} by profitable traders, ${list.length - prof} by large accounts` : "none seen yet"} since {fmtWhen(opens.tracking_since)}
        <HelpTip title="New positions"><p>Every tracked wallet is read about every 30 minutes. A coin and side it did not hold at the previous reading is a new position, drawn at its entry price: circles for profitable traders, squares for large accounts, bigger for larger positions (over $50K, over $500K). Timing is to the nearest reading.</p><p>Converging: two or more profitable traders open the same side within 24 hours, all still holding, the latest entry within 5% of the first, and at most two others already on that side. It is being recorded to test whether it leads price; until then it is information, not a signal.</p></HelpTip>
      </div>
      {convs.map((c, i) => (
        <div key={i}>
          <strong style={{ color: col(SIDE_COLOR[c.side]) }}>Converging</strong> · {fmtWhen(c.ts)} · {c.n} profitable traders opened {c.side} at {fmtPx(Math.min(c.first_px, c.last_px))} to {fmtPx(Math.max(c.first_px, c.last_px))}{c.others ? `, ${c.others} already on that side` : ""}
        </div>
      ))}
    </div>
  );
}
