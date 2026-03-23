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
        border: hovered ? `1px solid ${T.borderH}` : `1px solid ${T.border}`,
        borderRadius: T.radius,
        backdropFilter: "blur(20px) saturate(1.3)",
        WebkitBackdropFilter: "blur(20px) saturate(1.3)",
        boxShadow: glow
          ? `0 0 30px ${glow}, 0 0 0 1px rgba(255,255,255,0.03) inset, 0 1px 0 0 rgba(255,255,255,0.04) inset`
          : `${T.glassShadow}, 0 0 0 1px rgba(255,255,255,0.03) inset, 0 1px 0 0 rgba(255,255,255,0.04) inset`,
        transform: hovered ? "translateY(-1px)" : "translateY(0)",
        transition: "transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease",
        ...style,
      }}
    >
      {children}
    </div>
  );
}
