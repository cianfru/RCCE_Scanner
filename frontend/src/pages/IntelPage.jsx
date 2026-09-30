import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import GlassCard from "../components/GlassCard.jsx";
import FadeIn from "../components/FadeIn.jsx";
import HelpTip from "../components/HelpTip.jsx";
import Tabs from "../components/Tabs.jsx";
import useElementWidth from "../hooks/useElementWidth.js";
import { getAdminKey, setAdminKey } from "../auth.js";
import { pollWhileVisible } from "../utils/visiblePoll.js";
import { ago, areaPath, cellAlpha, countryName, firstDir, inviteStatus, linePath, monthStarts, niceMax, pct, points,
  shortDate, sortPeople } from "../utils/ownerIntel.js";
import "./intel.css";

// /intel: who uses Reflex, how much, from where, and the invite codes. The owner's only
// (the admin key, or the owner's wallet signed in); the data is /api/owner/intel.
const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const REFRESH_MS = 5 * 60_000;

const ownerHeaders = () => (getAdminKey() ? { "X-Admin-Key": getAdminKey() } : {});

async function fetchIntel() {
  const res = await fetch(`${API_BASE}/api/owner/intel`, { headers: ownerHeaders(), cache: "no-store" });
  if (res.status === 403) return { denied: true };
  if (!res.ok) throw new Error(`Server error ${res.status}`);
  return { data: await res.json() };
}

function Info({ title, children, width = 300 }) {
  return <HelpTip title={title} width={width} trigger="click" size={13}>{children}</HelpTip>;
}

const Check = () => (
  <span className="intel-yes" aria-label="yes">
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M3 8.5l3 3 7-7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
  </span>
);
const No = () => <span className="muted" aria-label="no">{"–"}</span>;

// ------------------------------------------------------------------ top line
function TopLine({ top }) {
  const w4 = top.week4;
  const logged = top.invited ? top.logged_in / top.invited : 0;
  return (
    <GlassCard className="intel-card">
      <div className="intel-kpis">
        <Kpi label="Today" value={top.today} info={<ActiveInfo />} />
        <Kpi label="7 days" value={top.d7} />
        <Kpi label="28 days" value={top.d28} />
        <div className="intel-kpi">
          <div className="intel-kpi-label">Logged in</div>
          <div className="intel-kpi-value">{top.logged_in}<small>/ {top.invited}</small></div>
          <div className="intel-meter" aria-hidden="true"><i style={{ width: `${Math.round(logged * 100)}%` }} /></div>
        </div>
        <div className="intel-kpi">
          <div className="intel-kpi-label">Week 4
            <Info title="Still here after 4 weeks">
              <p>The beta bar. Of the people whose first day was at least five weeks ago, the share that used Reflex at least once in their fourth week (days 28 to 34 after the first).</p>
              <p>People newer than that are not counted yet{w4.pending ? ` (${w4.pending} now)` : ""}.</p>
            </Info>
          </div>
          <div className="intel-kpi-value">{pct(w4.share)}</div>
          <div className="intel-kpi-foot">{w4.n ? `${w4.kept} of ${w4.n}` : "from week 5"}</div>
        </div>
      </div>
    </GlassCard>
  );
}

function Kpi({ label, value, info }) {
  return (
    <div className="intel-kpi">
      <div className="intel-kpi-label">{label}{info}</div>
      <div className="intel-kpi-value">{value}</div>
    </div>
  );
}

function ActiveInfo() {
  return (
    <Info title="Active people">
      <p>People who opened Reflex today, in the last 7 days and in the last 28 days, each counted once.</p>
      <p>Each invite code is one person. Everyone who logs in with the shared code counts as one.</p>
    </Info>
  );
}

// ------------------------------------------------------------------ daily active line
function DailyActive({ dau }) {
  const box = useRef(null);
  const width = useElementWidth(box) || 600;
  const [hover, setHover] = useState(null);
  const H = width < 520 ? 140 : 196, LEFT = 26, BOTTOM = 22;
  const w = Math.max(100, width - LEFT);
  const values = dau.map(d => d.n);
  const max = niceMax(Math.max(0, ...values));
  const pts = points(values, w, H, max);
  const months = monthStarts(dau);
  const onMove = e => {
    const r = e.currentTarget.getBoundingClientRect();
    const i = Math.round(((e.clientX - r.left - LEFT) / w) * (dau.length - 1));
    setHover(i >= 0 && i < dau.length ? i : null);
  };
  const h = hover != null ? pts[hover] : null;
  const total = values.reduce((a, b) => a + b, 0);
  return (
    <GlassCard className="intel-card">
      <div className="intel-head">Daily active
        <Info title="Daily active">
          <p>People who used Reflex each day, over the last 90 days.</p>
        </Info>
        <span className="intel-sub">90 days</span>
      </div>
      <div className="intel-dau" ref={box} onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
        <svg width={width} height={H + BOTTOM} role="img" aria-label={`Daily active people, last 90 days, ${total} person-days`}>
          <defs>
            <linearGradient id="intel-dau-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--t-accent)" stopOpacity="0.22" />
              <stop offset="100%" stopColor="var(--t-accent)" stopOpacity="0" />
            </linearGradient>
          </defs>
          {[0, 0.5, 1].map(f => (
            <g key={f}>
              <line x1={LEFT} x2={LEFT + w} y1={H - f * H} y2={H - f * H} stroke="var(--t-overlay08)" strokeWidth="1" />
              <text className="intel-axis" x={LEFT - 8} y={H - f * H + 4} textAnchor="end">{Math.round(f * max)}</text>
            </g>
          ))}
          {months.map(m => (
            <text key={m.i} className="intel-axis" x={LEFT + (pts[m.i]?.[0] || 0)} y={H + 17} textAnchor="middle">{m.label}</text>
          ))}
          <g transform={`translate(${LEFT},0)`}>
            <path d={areaPath(pts, H)} fill="url(#intel-dau-fill)" />
            <path d={linePath(pts)} fill="none" stroke="var(--t-accent)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
            {h && <>
              <line x1={h[0]} x2={h[0]} y1={0} y2={H} stroke="var(--t-overlay30)" strokeWidth="1" />
              <circle cx={h[0]} cy={h[1]} r="4" fill="var(--t-accent)" stroke="var(--t-bg)" strokeWidth="2" />
            </>}
          </g>
        </svg>
        {h && (
          <div className="intel-tip" style={{ left: Math.min(Math.max(LEFT + h[0], 60), width - 60) }}>
            {shortDate(dau[hover].day)} <b>{dau[hover].n}</b> {dau[hover].n === 1 ? "person" : "people"}
          </div>
        )}
      </div>
    </GlassCard>
  );
}

// ------------------------------------------------------------------ weekly retention
function Retention({ rows }) {
  const [on, setOn] = useState(null);
  const cols = Math.max(1, ...rows.map(r => r.cells.length));
  const cell = on ? rows[on[0]]?.cells[on[1]] : null;
  return (
    <GlassCard className="intel-card">
      <div className="intel-head">Weekly retention
        <Info title="Weekly retention" width={320}>
          <p>Each row is the week people first used Reflex, with how many. Each cell is the share of that row active in week 0, 1, 2 and on after it. Darker is more.</p>
        </Info>
      </div>
      {!rows.length ? <div className="intel-empty">No one yet.</div> : <>
        <div className="intel-grid" style={{ gridTemplateColumns: `max-content max-content repeat(${cols}, minmax(14px, 1fr))` }}
          onPointerLeave={() => setOn(null)}>
          <span /><span />
          {Array.from({ length: cols }, (_, k) => <span key={k} className="g-col">{k}</span>)}
          {rows.map((r, i) => [
            <span key={`l${i}`} className="g-row">{shortDate(r.week)}</span>,
            <span key={`s${i}`} className="g-size" title="people">{r.size}</span>,
            ...Array.from({ length: cols }, (_, k) => {
              const c = r.cells[k];
              if (!c) return <span key={k} />;
              const a = cellAlpha(c.share);
              return (
                <button key={k} type="button" className="intel-cell" data-on={on && on[0] === i && on[1] === k ? "true" : undefined}
                  aria-label={`Week of ${shortDate(r.week)}, week ${k}: ${c.n} of ${r.size}`}
                  style={{ background: a ? `color-mix(in srgb, var(--t-accent) ${Math.round(a * 100)}%, transparent)` : undefined }}
                  onPointerEnter={() => setOn([i, k])} onFocus={() => setOn([i, k])} onClick={() => setOn([i, k])} />
              );
            }),
          ])}
        </div>
        <div className="intel-readout">
          {cell ? <>Week of {shortDate(rows[on[0]].week)}, week {on[1]}: <b>{cell.n} of {rows[on[0]].size}</b> active ({pct(cell.share)})</>
            : <>Weeks since the first visit</>}
        </div>
      </>}
    </GlassCard>
  );
}

// ------------------------------------------------------------------ people
const PEOPLE_COLS = [
  ["label", "Person"], [null, "Last 28 days"], ["d7", "7d"], ["d28", "28d"], ["first_seen", "First"],
  ["last_seen", "Last"], [null, "Top features"], ["country", "Place"], ["device", "Device"],
  ["wallet", "Wallet"], ["telegram", "Telegram"],
];
const NUMERIC = new Set(["d7", "d28", "first_seen", "last_seen"]);

function People({ people, now }) {
  const [sort, setSort] = useState({ key: "last_seen", dir: "desc" });
  const rows = useMemo(() => sortPeople(people, sort.key, sort.dir), [people, sort]);
  const onSort = key => setSort(s => (s.key === key ? { key, dir: s.dir === "desc" ? "asc" : "desc" } : { key, dir: firstDir(key) }));
  if (!people.length) return <div className="intel-empty">No one yet.</div>;
  return (
    <div className="intel-scroll">
      <table className="intel-table intel-people">
        <thead>
          <tr>
            {PEOPLE_COLS.map(([key, label]) => (
              <th key={label} className={NUMERIC.has(key) ? "num" : undefined}>
                {key ? (
                  <button type="button" onClick={() => onSort(key)} aria-sort={sort.key === key ? (sort.dir === "asc" ? "ascending" : "descending") : undefined}>
                    {label}{sort.key === key && <span aria-hidden="true">{sort.dir === "asc" ? "↑" : "↓"}</span>}
                  </button>
                ) : label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(p => (
            <tr key={p.id} className={p.revoked ? "gone" : undefined}>
              <td className="who">{p.label}{p.revoked && <span className="muted"> revoked</span>}</td>
              <td>
                <span className="intel-strip" aria-label={`${p.d28} active days of the last 28`}>
                  {(p.recent || []).map((v, i) => <i key={i} className={v ? "on" : undefined} />)}
                </span>
              </td>
              <td className="num">{p.first_seen ? p.d7 : <No />}</td>
              <td className="num">{p.first_seen ? p.d28 : <No />}</td>
              <td className="num">{p.first_seen ? shortDate(p.first_seen) : <span className="muted">not yet</span>}</td>
              <td className="num">{p.last_seen ? ago(p.last_seen, now) : <No />}</td>
              <td>{p.top.length ? p.top.join(", ") : <No />}</td>
              <td>{p.country ? <>{p.country}{p.city && <span className="muted"> {p.city}</span>}</> : <No />}</td>
              <td>{p.device ? <>{cap(p.device)}{p.browser && <span className="muted"> {p.browser}</span>}</> : <No />}</td>
              <td>{p.wallet ? <Check /> : <No />}</td>
              <td>{p.telegram ? <Check /> : <No />}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const cap = s => (s ? s[0].toUpperCase() + s.slice(1) : s);

// ------------------------------------------------------------------ features
const SIDE_COLORS = { long: "var(--t-profit)", short: "var(--t-loss)", both: "var(--t-accent)" };

function Features({ features, sides }) {
  const used = features.filter(f => f.events > 0);
  const max = Math.max(1, ...used.map(f => f.events));
  const sideTotal = Object.values(sides || {}).reduce((a, b) => a + b, 0);
  const hasSplit = features.some(f => f.returning != null || f.once != null);
  return (
    <div className="intel-two">
      <div>
        <div className="intel-section">Use, last 28 days
          <Info title="Use">
            <p>How many times each feature was used in the last 28 days, and by how many people.</p>
          </Info>
        </div>
        {!used.length ? <div className="intel-empty">Nothing yet.</div> : (
          <div className="intel-bars">
            {used.map(f => [
              <span key={`n${f.key}`} className="b-name">{f.name}</span>,
              <span key={`b${f.key}`}><div className="intel-bar" style={{ width: `${(f.events / max) * 100}%` }} /></span>,
              <b key={`v${f.key}`} className="b-num">{f.events}</b>,
              <span key={`s${f.key}`} className="b-sub">{f.people} {f.people === 1 ? "person" : "people"}</span>,
            ])}
          </div>
        )}
        {sideTotal > 0 && (
          <div style={{ marginTop: 22 }}>
            <div className="intel-section">Radar side</div>
            <div className="intel-split" aria-hidden="true">
              {["long", "short", "both"].map(k => sides[k] ? <i key={k} style={{ flex: sides[k], background: SIDE_COLORS[k] }} /> : null)}
            </div>
            <div className="intel-split-keys">
              {["long", "short", "both"].map(k => <span key={k}>{cap(k)} <b>{pct((sides[k] || 0) / sideTotal)}</b></span>)}
            </div>
          </div>
        )}
      </div>
      <div>
        <div className="intel-section">Returning and one-time
          <Info title="Returning and one-time" width={320}>
            <p>The share of each group that has used a feature at least once. Returning people used Reflex on two days or more; one-time people on one day only.</p>
          </Info>
        </div>
        {!hasSplit ? <div className="intel-empty">Nothing yet.</div> : <>
          <div className="intel-legend"><span><i />Returning</span><span><i className="second" />One-time</span></div>
          <div className="intel-bars">
            {features.filter(f => (f.returning || 0) + (f.once || 0) > 0).map(f => [
              <span key={`n${f.key}`} className="b-name">{f.name}</span>,
              <span key={`b${f.key}`} className="intel-pair">
                <div className={`intel-bar${f.returning ? "" : " none"}`} style={{ width: `${(f.returning || 0) * 100}%` }} />
                <div className={`intel-bar second${f.once ? "" : " none"}`} style={{ width: `${(f.once || 0) * 100}%` }} />
              </span>,
              <b key={`v${f.key}`} className="b-num">{pct(f.returning)}</b>,
              <span key={`s${f.key}`} className="b-sub">{pct(f.once)}</span>,
            ])}
          </div>
        </>}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ places
function Places({ countries, devices }) {
  const max = Math.max(1, ...countries.map(c => c.people));
  const devTotal = Object.values(devices || {}).reduce((a, b) => a + b, 0);
  return (
    <div className="intel-two">
      <div>
        <div className="intel-section">Countries, last 28 days
          <Info title="Countries">
            <p>People and sessions per country over the last 28 days, with the most frequent cities. Only the country and city are kept, never an address.</p>
          </Info>
        </div>
        {!countries.length ? <div className="intel-empty">Nothing yet.</div> : (
          <div className="intel-bars">
            {countries.map(c => [
              <span key={`n${c.country}`} className="b-name">{countryName(c.country)}{c.cities.length > 0 && <div className="intel-city">{c.cities.join(", ")}</div>}</span>,
              <span key={`b${c.country}`}><div className="intel-bar" style={{ width: `${(c.people / max) * 100}%` }} /></span>,
              <b key={`v${c.country}`} className="b-num">{c.people}</b>,
              <span key={`s${c.country}`} className="b-sub">{c.sessions} sessions</span>,
            ])}
          </div>
        )}
      </div>
      <div>
        <div className="intel-section">Devices</div>
        {!devTotal ? <div className="intel-empty">Nothing yet.</div> : (
          <div className="intel-bars">
            {Object.entries(devices).sort((a, b) => b[1] - a[1]).map(([d, n]) => [
              <span key={`n${d}`} className="b-name">{cap(d)}</span>,
              <span key={`b${d}`}><div className="intel-bar" style={{ width: `${(n / devTotal) * 100}%` }} /></span>,
              <b key={`v${d}`} className="b-num">{n}</b>,
              <span key={`s${d}`} className="b-sub">{pct(n / devTotal)}</span>,
            ])}
          </div>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ invites
const EXPIRY = [{ key: "0", label: "No expiry" }, { key: "7", label: "7 days" }, { key: "30", label: "30 days" }, { key: "90", label: "90 days" }];

function Invites({ invites, now, onChange }) {
  const [label, setLabel] = useState("");
  const [days, setDays] = useState("0");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fresh, setFresh] = useState(null);
  const [copied, setCopied] = useState(null);
  const [confirm, setConfirm] = useState(null);

  const create = async e => {
    e.preventDefault();
    if (!label.trim() || busy) return;
    setBusy(true); setError("");
    try {
      const res = await fetch(`${API_BASE}/api/owner/invites`, {
        method: "POST", headers: { "Content-Type": "application/json", ...ownerHeaders() }, adminNotice: false,
        body: JSON.stringify({ label: label.trim(), expires_days: Number(days) || null }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || `Server error ${res.status}`);
      setFresh(body.id); setLabel("");
      copy(body);
      onChange();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };
  const copy = inv => {
    navigator.clipboard?.writeText(inv.code).then(() => { setCopied(inv.id); setTimeout(() => setCopied(c => (c === inv.id ? null : c)), 1600); }).catch(() => {});
  };
  const revoke = async inv => {
    if (confirm !== inv.id) { setConfirm(inv.id); return; }
    setConfirm(null);
    const res = await fetch(`${API_BASE}/api/owner/invites/${inv.id}`, { method: "DELETE", headers: ownerHeaders(), adminNotice: false });
    if (!res.ok) setError(`Could not revoke (${res.status})`);
    onChange();
  };

  return (
    <div>
      <form className="intel-new" onSubmit={create}>
        <input className="intel-input" value={label} onChange={e => setLabel(e.target.value)} maxLength={40}
          placeholder="Name" aria-label="Who the code is for" />
        <Tabs small label="Expiry" items={EXPIRY} value={days} onChange={setDays} />
        <button type="submit" className="intel-btn" disabled={busy || !label.trim()}>Create code</button>
        {error && <span className="intel-note">{error}</span>}
      </form>
      <div className="intel-scroll">
        <table className="intel-table">
          <thead>
            <tr><th>Person</th><th>Code</th><th>Status</th><th className="num">Logins</th><th className="num">Last login</th><th className="num">Created</th><th /></tr>
          </thead>
          <tbody>
            <tr>
              <td className="who">Shared code</td>
              <td className="muted">set on the server</td>
              <td className="intel-state-active">Active</td>
              <td className="num muted">{"–"}</td><td className="num muted">{"–"}</td><td className="num muted">{"–"}</td><td />
            </tr>
            {invites.map(inv => {
              const st = inviteStatus(inv, now);
              const live = st.key === "active" || st.key === "expires";
              return (
                <tr key={inv.id} className={`${fresh === inv.id ? "intel-fresh" : ""} ${live ? "" : "gone"}`}>
                  <td className="who">{inv.label}</td>
                  <td>
                    <span className="intel-code">{inv.code}</span>
                    {live && <button type="button" className="intel-link" onClick={() => copy(inv)}>{copied === inv.id ? "Copied" : "Copy"}</button>}
                  </td>
                  <td className={`intel-state-${st.key}`}>{st.text}</td>
                  <td className="num">{inv.logins || 0}</td>
                  <td className="num">{inv.last_login ? ago(inv.last_login, now) : <span className="muted">never</span>}</td>
                  <td className="num">{shortDate(inv.created)}</td>
                  <td>{live && (
                    <button type="button" className={`intel-link${confirm === inv.id ? " warn" : ""}`} onClick={() => revoke(inv)}
                      onBlur={() => setConfirm(c => (c === inv.id ? null : c))}>
                      {confirm === inv.id ? "Confirm revoke" : "Revoke"}
                    </button>
                  )}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ the owner check
function Gate({ onRetry }) {
  const [key, setKey] = useState(getAdminKey());
  return (
    <GlassCard className="intel-gate">
      <p>For the owner. Enter the admin key (kept in this browser only).</p>
      <form style={{ display: "flex", gap: 10 }} onSubmit={e => { e.preventDefault(); setAdminKey(key); onRetry(); }}>
        <input className="intel-input" type="password" autoComplete="off" value={key} onChange={e => setKey(e.target.value)} aria-label="Admin key" placeholder="Admin key" />
        <button type="submit" className="intel-btn" disabled={!key.trim()}>Open</button>
      </form>
    </GlassCard>
  );
}

// ------------------------------------------------------------------ page
const TABS = [{ key: "people", label: "People" }, { key: "features", label: "Features" }, { key: "places", label: "Places" }, { key: "invites", label: "Invites" }];

export default function IntelPage({ style }) {
  const [state, setState] = useState({ loading: true });
  const [tab, setTab] = useState("people");
  const load = useCallback(() => {
    fetchIntel().then(r => setState(r)).catch(e => setState(s => ({ ...s, loading: false, error: e.message })));
  }, []);
  useEffect(() => { load(); return pollWhileVisible(load, REFRESH_MS); }, [load]);

  const d = state.data;
  return (
    <FadeIn delay={100} style={style}>
      {state.denied ? <Gate onRetry={load} /> : !d ? (
        state.error ? <div className="intel-empty">{state.error}</div> : <div className="intel-empty" aria-busy="true" />
      ) : (
        <div className="intel">
          <TopLine top={d.top} />
          <div className="intel-charts">
            <DailyActive dau={d.dau} />
            <Retention rows={d.retention} />
          </div>
          <GlassCard className="intel-card">
            <div className="intel-tabs" style={{ marginBottom: 16 }}>
              <Tabs label="Intel view" items={TABS} value={tab} onChange={setTab} />
              {!d.recording && <span className="intel-note">Recording is off</span>}
            </div>
            {tab === "people" && <People people={d.people} now={d.now} />}
            {tab === "features" && <Features features={d.features} sides={d.radar_sides} />}
            {tab === "places" && <Places countries={d.countries} devices={d.devices} />}
            {tab === "invites" && <Invites invites={d.invites} now={d.now} onChange={load} />}
          </GlassCard>
        </div>
      )}
    </FadeIn>
  );
}
