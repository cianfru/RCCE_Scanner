// setInterval that skips ticks while the tab is hidden (a hidden tab's refreshes
// are never seen but still cost server egress). A tick missed while hidden runs
// as soon as the tab is visible again, so what the user sees is as fresh as before.
// Returns a stop function, for an effect's cleanup.
export function pollWhileVisible(fn, ms, doc = globalThis.document) {
  let missed = false;
  const id = setInterval(() => {
    if (doc?.hidden) { missed = true; return; }
    fn();
  }, ms);
  const onVisibility = () => {
    if (doc.hidden || !missed) return;
    missed = false;
    fn();
  };
  doc?.addEventListener?.("visibilitychange", onVisibility);
  return () => {
    clearInterval(id);
    doc?.removeEventListener?.("visibilitychange", onVisibility);
  };
}
