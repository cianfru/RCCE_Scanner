import GlassCard from "./GlassCard.jsx";
import { TableSkeleton } from "./Skeleton.jsx";

// Shown inside the page while a page's code loads: a glass card with a shimmering table.
export default function PageSkeleton({ style }) {
  return (
    <GlassCard style={{ overflow: "hidden", ...style }}>
      <div aria-busy="true" aria-label="Page loading">
        <TableSkeleton rows={12} cols={8} />
      </div>
    </GlassCard>
  );
}
