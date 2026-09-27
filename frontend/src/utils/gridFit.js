// Scanner grid fit (spec 4.3): which columns fit the grid's own width, and at which cell padding.
// Pure: the widths come from COLUMN_FIT, the container width from the caller.
import { COLUMN_FIT } from '../scannerColumns.js';

export const FIT_MARGIN = 8;          // slack for borders and rounding
export const PHONE_MAX = 640;         // container widths below this get the phone rows
const TIERS = [12, 10, 8];
const CHEAP = ['OI', '#'];            // cheap columns leave before the 8px tier, OI first
export const PHONE_SET = ['PRI', 'SYMBOL', 'REGIME', 'SIGNAL'];
// After the cheap ones, columns leave by rank: 3 (ENERGY) first, 12 (Z-SCORE) last.
export const RANKED = Object.entries(COLUMN_FIT)
  .filter(([, f]) => typeof f.rank === 'number')
  .sort((a, b) => a[1].rank - b[1].rank)
  .map(([label]) => label);
// Every column that may leave, in the order it leaves (the runtime safety net uses it too).
export const DROP_ORDER = [...CHEAP, ...RANKED];

export function neededWidth(labels, pad) {
  const i = TIERS.indexOf(pad);
  return labels.reduce((sum, label) => sum + (COLUMN_FIT[label]?.w[i] ?? 0), 0) + FIT_MARGIN;
}

/**
 * fitColumns(labels, W, { phone, extraDrops }) -> { visible, pad, hidden, phone }
 *   labels      candidate column labels, in display order (dead columns already removed)
 *   W           the grid wrapper's clientWidth
 *   phone       force the phone set (defaults to W < 640)
 *   extraDrops  columns to remove beyond the fit, next in drop order (runtime safety net)
 */
export function fitColumns(labels, W, { phone, extraDrops = 0 } = {}) {
  const hiddenFrom = visible => labels.filter(label => !visible.includes(label));
  if (phone ?? W < PHONE_MAX) {
    const visible = labels.filter(label => PHONE_SET.includes(label));
    return { visible, pad: 8, hidden: hiddenFrom(visible), phone: true };
  }
  let visible = [...labels];
  const fits = pad => neededWidth(visible, pad) <= W;
  let pad = [12, 10].find(fits) ?? null;
  // Cheap columns go before the padding shrinks to 8.
  for (const label of CHEAP) {
    if (pad != null) break;
    if (!visible.includes(label)) continue;
    visible = visible.filter(l => l !== label);
    pad = [12, 10].find(fits) ?? null;
  }
  if (pad == null) {
    pad = 8;
    for (const label of RANKED) {
      if (fits(8)) break;
      visible = visible.filter(l => l !== label);
    }
  }
  for (let i = 0; i < extraDrops; i++) {
    const next = DROP_ORDER.find(label => visible.includes(label));
    if (!next) break;
    visible = visible.filter(l => l !== next);
  }
  return { visible, pad, hidden: hiddenFrom(visible), phone: false };
}
