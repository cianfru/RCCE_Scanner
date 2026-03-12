import { useState } from "react";
import { T } from "../theme.js";

export default function GlassCard({ children, style = {}, glow = null, hoverable = false, className = "", onClick }) {
  const [hovered, setHovered] = useState(false);
  return (
    <div
      className={className}
      onClick={onClick}
      onMouseEnter={() => hoverable && setHovered(true)}
      onMouseLeave={() => hoverable && setHovered(false)}
      style={{
        background: T.glassBg,
        border: `1px solid ${T.border}`,
        borderRadius: T.radius,
        backdropFilter: "blur(16px) saturate(1.2)",
        WebkitBackdropFilter: "blur(16px) saturate(1.2)",
        boxShadow: glow
          ? `0 0 30px ${glow}, ${T.glassInset}`
          : `${T.glassShadow}, ${T.glassInset}`,
        transform: hovered ? "scale(1.01)" : "scale(1)",
        transition: "transform 0.2s ease, box-shadow 0.2s ease",
        ...style,
      }}
    >
      {children}
    </div>
  );
}
