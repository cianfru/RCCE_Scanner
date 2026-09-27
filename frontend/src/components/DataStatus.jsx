import { T } from "../theme.js";

// One line of feed status: a 6px dot (grey loading, amber failed, mint fresh), the sentence,
// and an underlined Retry when it failed. Flat text, no box.
export default function DataStatus({ loading, error, updatedAt, onRetry, label = "Data" }) {
  if (!loading && !error && !updatedAt) return null;
  const dot = loading ? T.text3 : error ? T.yellow : T.accent;
  return (
    <div className="data-status" role={error ? "alert" : "status"}>
      <span className="data-status-dot" style={{ background: dot }} aria-hidden="true" />
      <span style={{ color: error ? T.text2 : T.text3 }}>
        {loading ? `Loading ${label.toLowerCase()}…`
          : error ? `${label} could not refresh.${updatedAt ? " Showing the last successful reading." : " No reading is available yet."}`
          : `${label} updated`}
        {updatedAt && !loading && <> <time dateTime={new Date(updatedAt).toISOString()}>{new Date(updatedAt).toLocaleString()}</time></>}
      </span>
      {error && onRetry && <button type="button" className="te-link" onClick={onRetry}>Retry</button>}
    </div>
  );
}
