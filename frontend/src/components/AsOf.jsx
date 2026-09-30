// A small muted "as of HH:MM" beside a panel whose feed the server answered from its last
// good copy (backend/degrade.py). Renders nothing while the data is current.
import { T } from "../theme.js";
import { asOfLabel, stalest } from "../utils/asOf.js";

export default function AsOf({ data, also, style }) {
  const label = asOfLabel(also ? stalest(data, also) : data);
  if (!label) return null;
  return (
    <span className="as-of" style={{ fontSize: 11, color: T.text3, fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap", ...style }}>
      {label}
    </span>
  );
}
