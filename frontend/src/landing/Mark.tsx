// Reflex "Measured Pulse" mark — ported verbatim from the design kit.
export function Mark({ size = 31 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <path
        d="M5 26H12L20 10L29 38L36 22H43"
        stroke="currentColor"
        strokeWidth="4.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
