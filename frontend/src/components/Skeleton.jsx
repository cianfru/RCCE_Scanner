import { T } from "../theme.js";

/** Shimmer loading skeleton — width/height in px or CSS string. */
export function Skeleton({ width = "100%", height = 14, borderRadius = 6, style = {} }) {
  return (
    <div
      className="shimmer-loading"
      style={{
        width: typeof width === "number" ? `${width}px` : width,
        height: typeof height === "number" ? `${height}px` : height,
        borderRadius,
        ...style,
      }}
    />
  );
}

/** Skeleton row mimicking a table row with N cells. */
export function SkeletonRow({ cells = 6, height = 12 }) {
  return (
    <div style={{
      display: "flex", gap: 12, padding: "10px 16px",
      borderBottom: `1px solid ${T.overlay04}`,
    }}>
      {Array.from({ length: cells }).map((_, i) => (
        <Skeleton
          key={i}
          width={i === 0 ? 80 : 50 + Math.random() * 40}
          height={height}
        />
      ))}
    </div>
  );
}

/** Full table skeleton: header + N rows. */
export function TableSkeleton({ rows = 8, cols = 6 }) {
  return (
    <div>
      {/* Header */}
      <div style={{
        display: "flex", gap: 12, padding: "12px 16px",
        borderBottom: `1px solid ${T.overlay08}`,
        background: T.overlay02,
      }}>
        {Array.from({ length: cols }).map((_, i) => (
          <Skeleton key={i} width={50 + i * 10} height={10} borderRadius={4} />
        ))}
      </div>
      {/* Rows */}
      {Array.from({ length: rows }).map((_, i) => (
        <SkeletonRow key={i} cells={cols} />
      ))}
    </div>
  );
}

/** Card skeleton for stat cards / summary areas. */
export function CardSkeleton({ count = 4 }) {
  return (
    <div style={{ display: "flex", gap: 10, flexWrap: "wrap", padding: 16 }}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} style={{
          flex: "1 1 120px", padding: "14px 16px",
          borderRadius: 12,
          background: T.overlay04,
          border: `1px solid ${T.overlay06}`,
          display: "flex", flexDirection: "column", gap: 8,
        }}>
          <Skeleton width={60} height={10} />
          <Skeleton width={90} height={22} />
        </div>
      ))}
    </div>
  );
}
