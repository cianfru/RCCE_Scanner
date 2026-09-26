// Small chart icon beside an (i): opens the market history drawer.
export default function HistoryButton({ label, onClick }) {
  return <button type="button" className="history-btn" aria-label={label} title={label} onClick={onClick}>
    <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">
      <polyline points="1,9 4,5.5 6.5,7.5 11,2" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  </button>;
}
