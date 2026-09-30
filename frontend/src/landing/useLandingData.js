// The landing's live data: one small public payload (/api/public/landing), the same for every
// visitor. It is read through this site's own /edge/api/ path, where the CDN keeps a copy, so
// most visits never reach the API; straight from the API when that path is not there (local
// builds); and from the snapshot bundled with the page when both fail. Read once per visit.
import { useEffect, useState } from "react";
import { EDGE_ALLOWED } from "../edge.js";
import { hydrate } from "../utils/landingData.js";

const API_BASE = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");
const PATH = "/api/public/landing";

async function json(url) {
  const res = await fetch(url, { headers: { accept: "application/json" } });
  if (!res.ok || !(res.headers.get("content-type") || "").includes("application/json")) throw new Error("not the payload");
  const body = hydrate(await res.json());
  if (!body || !body.coins.length) throw new Error("empty");
  return body;
}

let shared = null;
function load() {
  if (shared) return shared;
  const direct = () => json(`${API_BASE}${PATH}`);
  shared = (EDGE_ALLOWED ? json(`/edge${PATH}`).catch(direct) : direct())
    .then(body => ({ body, live: true }))
    .catch(() => import("./snapshot.json").then(m => ({ body: hydrate(m.default), live: false })));
  return shared;
}

export default function useLandingData() {
  const [state, setState] = useState(null);
  useEffect(() => {
    let on = true;
    load().then(s => { if (on) setState(s); });
    return () => { on = false; };
  }, []);
  return state;
}
