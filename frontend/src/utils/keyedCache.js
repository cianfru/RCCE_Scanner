// A small keyed cache for shared API reads (tested in keyedCache.test.js): the setup map
// per timeframe, the watch list, and open positions per address.
//  - One request in flight per key; callers share its promise.
//  - load(key) returns the cached data while it is younger than ttl.
//  - With refresh on, each key has one timer while it has subscribers: it reloads when
//    the data turns ttl old, and skips while the page is hidden (resume() picks it up).
//  - A failed read keeps the last data and records the error.
// get(key) returns a snapshot {data, error, loading} whose identity only changes when
// the entry does, so React's useSyncExternalStore can read it directly.

const EMPTY = Object.freeze({ data: undefined, error: null, loading: false });

export function createKeyedCache({
  fetcher,
  ttl = 300_000,
  refresh = false,
  now = () => Date.now(),
  isHidden = () => typeof document !== "undefined" && !!document.hidden,
  setTimer = (fn, ms) => setTimeout(fn, ms),
  clearTimer = t => clearTimeout(t),
}) {
  const entries = new Map();

  const entry = key => {
    let e = entries.get(key);
    if (!e) {
      e = { data: undefined, ts: 0, tried: 0, error: null, promise: null, subs: new Set(), timer: null, snap: null };
      entries.set(key, e);
    }
    return e;
  };
  const emit = e => {
    e.snap = null;
    for (const fn of [...e.subs]) fn();
  };
  const fresh = e => e.data !== undefined && now() - e.ts < ttl;

  function load(key, { force = false } = {}) {
    const e = entry(key);
    if (e.promise) return e.promise;
    if (!force && fresh(e)) return Promise.resolve(e.data);
    const p = Promise.resolve()
      .then(() => fetcher(key))
      .then(
        d => { e.data = d; e.ts = now(); e.error = null; },
        err => { e.error = err || new Error("failed"); },
      )
      .then(() => {
        e.tried = now();
        e.promise = null;
        emit(e);
        return e.data;
      });
    e.promise = p;
    emit(e);
    return p;
  }

  function schedule(e, key) {
    if (e.timer != null) { clearTimer(e.timer); e.timer = null; }
    if (!refresh || e.subs.size === 0) return;
    const last = Math.max(e.ts, e.tried);
    const wait = Math.max(1000, last + ttl - now());
    e.timer = setTimer(() => {
      e.timer = null;
      if (e.subs.size === 0 || isHidden()) return;
      if (now() - Math.max(e.ts, e.tried) < ttl - 1000) { schedule(e, key); return; }
      load(key, { force: true }).then(() => schedule(e, key));
    }, wait);
  }

  function subscribe(key, fn) {
    const e = entry(key);
    e.subs.add(fn);
    if (e.subs.size === 1) {
      if (fresh(e)) schedule(e, key);
      else load(key).then(() => schedule(e, key));
    }
    return () => {
      e.subs.delete(fn);
      if (e.subs.size === 0 && e.timer != null) { clearTimer(e.timer); e.timer = null; }
    };
  }

  function get(key) {
    const e = entries.get(key);
    if (!e) return EMPTY;
    if (!e.snap) e.snap = Object.freeze({ data: e.data, error: e.error, loading: !!e.promise });
    return e.snap;
  }

  // After the page was hidden: reload what went stale for keys that are on screen.
  function resume() {
    for (const [key, e] of entries) {
      if (!e.subs.size) continue;
      if (fresh(e) || e.promise) schedule(e, key);
      else load(key).then(() => schedule(e, key));
    }
  }

  return { load, subscribe, get, resume, peek: key => entries.get(key)?.data };
}
