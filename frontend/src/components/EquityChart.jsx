import { useEffect, useRef, useState } from "react";
import { T } from "../theme.js";
import { fmtUsd as fmt$ } from "../utils/hyperlens.js";

// Account value over time: a line with a soft fill, three value labels and the latest value.
// data: [{timestamp, value}] or plain numbers. The wallet dialog and the trader profile use it.
export default function EquityChart({ data, width = 500, height = 120, emptyText = "Collecting equity data..." }) {
  const containerRef = useRef(null);
  const [cw, setCw] = useState(width);
  useEffect(() => {
    if (containerRef.current) setCw(containerRef.current.offsetWidth);
    const ro = new ResizeObserver(([e]) => setCw(e.contentRect.width));
    if (containerRef.current) ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  if (!data || data.length < 2) {
    return (
      <div ref={containerRef} style={{ width: "100%", height, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <span style={{ fontFamily: T.mono, fontSize: T.textXs, color: T.text4 }}>{emptyText}</span>
      </div>
    );
  }

  const values = data.map(d => d.value ?? d);
  const minV = Math.min(...values);
  const maxV = Math.max(...values);
  const range = maxV - minV || 1;
  const pad = { top: 8, right: 6, bottom: 6, left: 54 };
  const chartW = cw - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom;
  const isUp = values[values.length - 1] >= values[0];
  const lineColor = isUp ? T.green : T.red;

  const points = values.map((v, i) => ({
    x: pad.left + (i / (values.length - 1)) * chartW,
    y: pad.top + chartH - ((v - minV) / range) * chartH,
  }));

  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const areaPath = `${linePath} L${(pad.left + chartW).toFixed(1)},${(pad.top + chartH).toFixed(1)} L${pad.left},${(pad.top + chartH).toFixed(1)} Z`;
  const gradId = `eq-${Math.random().toString(36).slice(2, 8)}`;

  // Y-axis: 3 labels
  const yLabels = [maxV, (maxV + minV) / 2, minV];

  return (
    <div ref={containerRef} style={{ width: "100%" }}>
      <svg width={cw} height={height} viewBox={`0 0 ${cw} ${height}`} style={{ display: "block" }}>
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={lineColor} stopOpacity="0.18" />
            <stop offset="100%" stopColor={lineColor} stopOpacity="0.01" />
          </linearGradient>
        </defs>
        {yLabels.map((v, i) => {
          const y = pad.top + chartH - ((v - minV) / range) * chartH;
          return (
            <g key={i}>
              <line x1={pad.left} y1={y} x2={cw - pad.right} y2={y}
                stroke={T.border} strokeWidth="0.5" strokeDasharray="3,3" opacity="0.5" />
              <text x={pad.left - 4} y={y + 4} textAnchor="end" fill={T.text4}
                fontFamily={T.mono} fontSize="12">{fmt$(v)}</text>
            </g>
          );
        })}
        <path d={areaPath} fill={`url(#${gradId})`} />
        <path d={linePath} fill="none" stroke={lineColor} strokeWidth="1.5" strokeLinejoin="round" />
        <circle cx={points[points.length - 1].x} cy={points[points.length - 1].y} r="3" fill={lineColor} />
        <text x={cw - pad.right} y={Math.max(points[points.length - 1].y - 6, 12)}
          textAnchor="end" fill={lineColor} fontFamily={T.mono} fontSize="12" fontWeight="700">
          {fmt$(values[values.length - 1])}
        </text>
      </svg>
    </div>
  );
}
