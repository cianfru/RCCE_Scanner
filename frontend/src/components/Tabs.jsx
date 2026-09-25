// One tab style across the product: the scanner's underlined timeframe tabs.
export default function Tabs({ items, value, onChange, small = false, label }) {
  return <div className={`reflex-tabs${small ? " reflex-tabs-small" : ""}`} role="group" aria-label={label}>
    {items.map(({ key, label: text }) => (
      <button key={key} type="button" aria-pressed={value === key} onClick={() => onChange(key)}>{text}</button>
    ))}
  </div>;
}
