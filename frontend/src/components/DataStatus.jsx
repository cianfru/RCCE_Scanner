import { T } from "../theme.js";

// One line of feed status: the sentence, and an underlined Retry when it failed.
// Flat text, no box, no status dot.
export default function DataStatus({ loading, error, updatedAt, onRetry, label = "Data" }) {
  if (!loading && !error && !updatedAt) return null;
  return (
    <div className="data-status" role={error ? "alert" : "status"}>
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
