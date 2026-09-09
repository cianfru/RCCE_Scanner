// Reflex R symbol (metallic ribbon) — used for small inline marks.
export function Mark({ size = 31 }: { size?: number }) {
  return (
    <img
      src="/reflex-mark.png"
      alt=""
      width={size}
      height={size}
      style={{ display: 'inline-block', objectFit: 'contain', verticalAlign: 'middle' }}
    />
  );
}
