import { useEffect, useRef, useState } from "react";

// The coin chart's Layers control: one button that opens a list of switches in groups. Any number can be on;
// the list stays open while they are changed and closes on a tap outside or Escape.
// groups: utils/chartLayers.menuGroups; count: how many are on; maxHeight: the room under the toolbar (the list
// scrolls inside it, since the chart's panel clips what leaves it).
export default function ChartLayersMenu({ groups, count, onToggle, onClear, maxHeight }) {
  const [open, setOpen] = useState(false);
  const root = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const close = e => {
      if (e.key === "Escape" || (e.type === "pointerdown" && !root.current?.contains(e.target))) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", close);
    return () => { document.removeEventListener("pointerdown", close); document.removeEventListener("keydown", close); };
  }, [open]);
  return (
    <span className="chart-layers-menu" ref={root}>
      <button type="button" className="chart-layers-btn" aria-haspopup="true" aria-expanded={open} onClick={() => setOpen(o => !o)}>
        Layers{count ? ` ${count}` : ""}
      </button>
      {open && (
        <div className="chart-layers-panel" role="group" aria-label="Chart layers" style={maxHeight ? { maxHeight } : undefined}>
          {groups.filter(g => g.items.length).map(g => (
            <div key={g.key} className="chart-layers-group" role="group" aria-label={g.label}>
              <span className="chart-layers-heading">{g.label}</span>
              {g.items.map(it => (
                <button key={it.key} type="button" role="menuitemcheckbox" aria-checked={it.on} className="chart-layers-item" onClick={() => onToggle(it.key)}>
                  <span className="chart-layers-box" aria-hidden="true" />
                  <span className="chart-layers-name">{it.label}</span>
                  {it.note && <i>{it.note}</i>}
                </button>
              ))}
            </div>
          ))}
          <button type="button" className="chart-layers-clear" disabled={!count} onClick={onClear}>Clear all</button>
        </div>
      )}
    </span>
  );
}
