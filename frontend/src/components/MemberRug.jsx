// One tick per market in a group, on the same ±D-point scale in every chip: the dashed
// line is the typical alt, the bold mark the group's median, chevrons markets beyond the scale.
const X0 = 69, HALF = 57, MAX_EDGE = 3;

export default function MemberRug({ members, median, D }) {
  const x = e => X0 + (Math.max(-D, Math.min(D, e)) / D) * HALF;
  const inside = members.filter(m => Math.abs(m.e) <= D);
  const right = members.filter(m => m.e > D).slice(0, MAX_EDGE);
  const left = members.filter(m => m.e < -D).slice(0, MAX_EDGE);
  return <svg className="sector-rug" viewBox="0 0 138 14" width="138" height="14" aria-hidden="true">
    <line className="rug-zero" x1={X0} x2={X0} y1={0} y2={14} />
    {inside.map(m => <line key={m.sym} className="rug-tick" x1={x(m.e)} x2={x(m.e)} y1={3} y2={11} />)}
    {right.map((m, j) => <polyline key={`r${m.sym}`} className="rug-edge" points={`${128 + 3 * j},4 ${131 + 3 * j},7 ${128 + 3 * j},10`} />)}
    {left.map((m, j) => <polyline key={`l${m.sym}`} className="rug-edge" points={`${10 - 3 * j},4 ${7 - 3 * j},7 ${10 - 3 * j},10`} />)}
    {median != null && <rect className="rug-median" x={x(median) - 1.25} y={0} width={2.5} height={14} rx={1} />}
  </svg>;
}
