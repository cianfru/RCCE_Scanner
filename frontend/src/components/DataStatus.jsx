import { T } from "../theme.js";
export default function DataStatus({ loading, error, updatedAt, onRetry, label = "Data" }) {
  if (!loading && !error && !updatedAt) return null;
  return <div className="data-status" role={error ? "alert" : "status"} style={{color:error ? T.yellow : T.text3}}>
    <span>{loading ? `Loading ${label.toLowerCase()}…` : error ? `${label} could not refresh.${updatedAt ? " Showing the last successful reading." : " No reading is available yet."}` : `${label} updated`}
    {updatedAt && !loading && <> <time dateTime={new Date(updatedAt).toISOString()}>{new Date(updatedAt).toLocaleString()}</time></>}</span>
    {error && onRetry && <button type="button" onClick={onRetry}>Retry</button>}
  </div>;
}
