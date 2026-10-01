// The public landing at "/". Live visuals come from one small public payload
// (/api/public/landing, through the CDN; useLandingData.js), with a bundled snapshot when it
// cannot be read. The screen crops in public/landing/ are dated stills of the app.
// Copy stays generic: no counts that change; numbers appear only as readouts inside visuals.
import { useEffect, useMemo, useRef, useState } from "react";
import RadarMap from "../components/radar/RadarMap.jsx";
import Tabs from "../components/Tabs.jsx";
import HelpTip from "../components/HelpTip.jsx";
import DataTable from "../components/DataTable.jsx";
import LogoSculpture from "./LogoSculpture.jsx";
import { Mark, LogoLettering } from "./Mark";
import { SIDES, visible } from "../utils/setupMap.js";
import { moneyMode } from "../utils/radarDepth.js";
import { friendlyReason } from "../utils/signalPresentation.js";
import { applyTheme, themeVars, REGIME_META } from "../theme.js";
import { SCANNER_COLUMNS } from "../scannerColumns.js";
import useViewport from "../hooks/useViewport.js";
import useLandingData from "./useLandingData.js";
import FoldDiagram from "./FoldDiagram.jsx";
import HistoryChart from "./HistoryChart.jsx";
import "../terminal.css";
import "./palette.css";
import "./landing.css";

const DARK_VARS = themeVars("dark");
const IMG = "/landing/";
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const dayLabel = sec => { const d = new Date(sec * 1000); return `${WEEKDAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`; };
const hm = sec => { const d = new Date(sec * 1000); return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
const lastDailyClose = sec => Math.floor(sec / 86400) * 86400;
const reducedMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
const TITLE = "Reflex: market regimes and trader positioning for Hyperliquid";
const ACCESS = "/scanner";      // the access-code screen (the app's login gate)

// The brief in the phone: the caption the bot composed (backend tg_brief.compose) for the
// same morning as brief.webp, a dated still like the other crops.
const BRIEF = [
  "Risk-on · 86% in Uptrend · risk-on run day 41", "Fear &amp; Greed 71", "",
  "<b>Early setups</b>", "<b>FET</b> · 6 traders · $359K · in entry zone",
  "<b>MET</b> · new · 5 traders · $603K · in entry zone", "<b>CC</b> · 4 traders · $49K · in entry zone", "",
  "<a>Open Radar</a>",
];

function Info({ title, children }) {
  return <HelpTip title={title} width={340} trigger="click" label={`About: ${title}`}>{children}</HelpTip>;
}

function Nav() {
  return <header className="lp-nav lp-width">
    <a className="lp-brand" href="/" aria-label="Reflex home"><Mark size={34} /><LogoLettering /></a>
    <nav aria-label="Sections"><a href="#radar">Radar</a><a href="#engine">Engine</a><a href="#traders">Traders</a><a href="#history">History</a></nav>
    <a className="lp-cta lp-cta-ghost" href={ACCESS}>Open Reflex</a>
  </header>;
}

const NONE = new Set();
const NO_POSITIONS = new Map();
function HeroRadar({ data, phone }) {
  const [side, setSide] = useState("long");
  const coins = data?.coins || [];
  const pts = useMemo(() => visible(coins, { side }), [coins, side]);
  const byCoin = useMemo(() => new Map(coins.map(c => [c.coin, c])), [coins]);
  return <div className="lp-hero-radar radar-page" style={DARK_VARS}>
    <div className="lp-hero-radar-head">
      <Tabs small label="Traders' side" items={SIDES} value={side} onChange={setSide} />
      {data?.as_of && <span className="lp-stamp">1D close, {dayLabel(lastDailyClose(data.as_of))}</span>}
    </div>
    <div className="lp-hero-map">
      <RadarMap pts={pts} byCoin={byCoin} box={data?.box || { z: [-0.5, 1.5], n: [1, 8] }} data={data} tf="1d" height={phone ? 340 : 440}
        focus={null} watched={NONE} mineBy={NO_POSITIONS} mineOn={false} keep={NONE} onPick={() => {}} onRest={() => {}} moneyOn={moneyMode(coins)} side={side} />
      {/* The up axis, written along it, so it never sits under a bubble at the top of the map. */}
      <span className="lp-yaxis" aria-hidden="true">{side === "short" ? "More profitable traders short" : "More profitable traders long"}</span>
    </div>
  </div>;
}

function Coverage({ asOf }) {
  return <section className="lp-coverage lp-width" aria-label="Coverage">
    <div><b>Hyperliquid</b><span>perps and spot markets</span></div>
    <div><b>Traders</b><span>profitable and large wallets</span></div>
    <div><b>Since 2021</b><span>daily history</span></div>
    <div><b className="lp-mono">{asOf ? hm(asOf) : "—"}</b><span>{asOf ? `last scan, ${dayLabel(asOf)}` : "last scan"}</span></div>
  </section>;
}

function Layer({ id, kicker, title, line, info, children }) {
  return <section className="lp-layer lp-width" id={id} aria-labelledby={`${id}-h`}>
    <div className="lp-layer-copy">
      <span className="lp-kicker">{kicker}</span>
      <h2 id={`${id}-h`}>{title}</h2>
      <p>{line} <Info title={info.title}>{info.body}</Info></p>
    </div>
    <div className="lp-layer-art">{children}</div>
  </section>;
}

// Numbered marks on the Radar crop; positions are shares of the crop (996 x 514 at 1x).
const CALLOUTS = [
  { x: 24.2, y: 12.5, t: "Many profitable traders long, and the most money held" },
  { x: 35.6, y: 61, t: "Early setups: little stretch, a few traders in" },
  { x: 68.3, y: 32.9, t: "Ring: how far price is above the weekly band" },
  { x: 86, y: 84, t: "Stretched: far above its own average" },
];
function RadarCrop() {
  return <figure className="lp-shot lp-callouts">
    <div className="lp-shot-img">
      <img src={`${IMG}radar-map.webp`} width="996" height="514" alt="The Radar map at a daily close" loading="lazy" />
      {CALLOUTS.map((c, i) => <span key={i} className="lp-mark" style={{ left: `${c.x}%`, top: `${c.y}%` }}>{i + 1}</span>)}
    </div>
    <ol className="lp-mark-list">{CALLOUTS.map((c, i) => <li key={i}><span className="lp-mark">{i + 1}</span>{c.t}</li>)}</ol>
  </figure>;
}

// Plain words for an entry check that is not met, and for the engine's own warnings.
function againstList(row) {
  const words = {
    bullish_regime: () => `Regime is ${REGIME_META[row.regime]?.name || row.regime}; entries need Uptrend or Accumulation`,
    z_range: () => `Z-score ${Number(row.zscore).toFixed(2)}, outside the entry range`,
    not_greedy: () => "Fear & Greed is high",
    hl_whale_aligned: () => "Tracked wallets are not aligned with it",
    hl_not_counter: () => "Tracked wallets lean against it",
  };
  const failed = (row.conditions_detail || []).filter(c => c.available !== false && !c.met);
  return [
    ...failed.map(c => (words[c.name] ? words[c.name]() : `${c.label}: not met`)),
    ...(row.signal_warnings || []).map(w => friendlyReason(w?.message ?? w)),
  ];
}

function EngineRow({ row, phone }) {
  if (!row) return <div className="lp-engine lp-engine-empty" />;
  const cols = SCANNER_COLUMNS.filter(([, l]) => (phone ? ["SYMBOL", "REGIME", "SIGNAL", "COND"] : ["PRI", "SYMBOL", "REGIME", "SIGNAL", "Z-SCORE", "COND"]).includes(l));
  const checks = row.conditions_detail || [];
  const against = againstList(row);
  return <div className="lp-engine reflex-terminal" style={DARK_VARS}>
    <div className="lp-row-table"><DataTable results={[row]} sortKey="priority_score" onSort={() => {}} visibleColumns={cols} isMobile={phone} onSelect={() => {}} /></div>
    <div className="lp-expand">
      <div className="lp-checks">
        <span className="lp-sub">Checks · {row.conditions_met}/{row.conditions_total}</span>
        <ul>{checks.map(c => <li key={c.name} className={c.met ? "met" : ""}><i aria-hidden="true">{c.met ? "✓" : "–"}</i>{c.label}</li>)}</ul>
      </div>
      <div className="lp-against">
        <span className="lp-sub">Against it now</span>
        {against.length ? <ul>{against.map(t => <li key={t}>{t}</li>)}</ul> : <p className="lp-none">Nothing at this close.</p>}
      </div>
    </div>
  </div>;
}

function TraderShots() {
  return <div className="lp-traders">
    <figure className="lp-shot">
      <img src={`${IMG}trader-id.webp`} width="1238" height="66" alt="A profitable wallet, under its codename" loading="lazy" />
      <img src={`${IMG}trader-pos.webp`} width="1238" height="542" alt="Its HYPE long: every fill on the chart, and the average entry" loading="lazy" />
    </figure>
    <figure className="lp-shot">
      <img src={`${IMG}trader-rows.webp`} width="1352" height="198" alt="The largest profitable traders in HYPE" loading="lazy" />
    </figure>
  </div>;
}

function Phone() {
  return <div className="lp-phone" aria-label="The morning brief in Telegram">
    <div className="lp-phone-bar"><span className="lp-phone-avatar"><Mark size={18} /></span><b>Reflex</b><span>bot</span></div>
    <div className="lp-phone-chat">
      <div className="lp-bubble">
        <img src={`${IMG}brief.webp`} width="800" height="500" alt="The brief's Radar picture" loading="lazy" />
        <div className="lp-caption">{BRIEF.map((l, i) => (l ? <p key={i} dangerouslySetInnerHTML={{ __html: l }} /> : <br key={i} />))}</div>
      </div>
    </div>
  </div>;
}

function ForwardCounter({ f }) {
  if (!f || !f.next_report_day) return null;
  const day = Math.min(f.days_logged || 0, f.next_report_day);
  const declared = new Date(`${f.declared}T00:00:00Z`);
  return <div className="lp-counter">
    <div className="lp-counter-num"><b>Day {day}</b><span>of {f.next_report_day}</span></div>
    <div className="lp-counter-cells" style={{ gridTemplateColumns: `repeat(${f.next_report_day},1fr)` }} aria-hidden="true">
      {Array.from({ length: f.next_report_day }, (_, i) => <i key={i} className={i < day ? "on" : ""} />)}
    </div>
    <p>The Radar's forward test, declared {declared.getUTCDate()} {MONTHS[declared.getUTCMonth()]} {declared.getUTCFullYear()}.
      <Info title="The declared study">
        <p>The rules and the pass bar were committed before any result was computed.</p>
        <p>The first report is due at day {f.next_report_day}, with at least {f.min_events} events on {f.min_coins} coins. Until the bar is met, the Radar is context, not a signal.</p>
      </Info>
    </p>
  </div>;
}

// The floating ribbon at the top: the 3D R turns, bobs and leans toward the pointer, with its
// halo and floor shadow, only while it is on screen, the tab is visible and motion is not
// paused (Pause motion) or reduced (then it is a still frame).
function HeroArt({ reduced }) {
  const ref = useRef(null), tilt = useRef(null);
  const [seen, setSeen] = useState(true);
  const [shown, setShown] = useState(true);
  const [paused, setPaused] = useState(false);
  const active = !reduced && !paused && seen && shown;
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") return undefined;
    const io = new IntersectionObserver(([e]) => setSeen(e.isIntersecting), { rootMargin: "80px" });
    io.observe(el);
    const vis = () => setShown(!document.hidden);
    document.addEventListener("visibilitychange", vis);
    return () => { io.disconnect(); document.removeEventListener("visibilitychange", vis); };
  }, []);
  // Pointer lean, eased toward the pointer (mouse only), back to rest when motion stops.
  useEffect(() => {
    const el = tilt.current;
    if (!el) return undefined;
    if (!active) { el.style.transform = ""; return undefined; }
    let goal = [0, 0], now = [0, 0], frame = 0;
    const step = () => {
      now = [now[0] + (goal[0] - now[0]) * 0.06, now[1] + (goal[1] - now[1]) * 0.06];
      el.style.transform = `translate3d(${(now[0] * 16).toFixed(2)}px,${(now[1] * 11).toFixed(2)}px,0) rotate(${(now[0] * 0.8).toFixed(3)}deg)`;
      frame = Math.abs(goal[0] - now[0]) + Math.abs(goal[1] - now[1]) > 0.002 ? requestAnimationFrame(step) : 0;
    };
    const move = e => {
      if (e.pointerType !== "mouse") return;
      goal = [Math.max(-1, Math.min(1, (e.clientX / window.innerWidth - 0.5) * 2)), Math.max(-1, Math.min(1, (e.clientY / window.innerHeight - 0.5) * 2))];
      if (!frame) frame = requestAnimationFrame(step);
    };
    window.addEventListener("pointermove", move, { passive: true });
    return () => { window.removeEventListener("pointermove", move); cancelAnimationFrame(frame); el.style.transform = ""; };
  }, [active]);
  return <div className="lp-hero-art" ref={ref} data-moving={active ? "true" : "false"}>
    <div className="lp-r" aria-hidden="true" ref={tilt}>
      <div className="lp-r-float">
        <div className="lp-r-halo" />
        <LogoSculpture active={active} />
      </div>
      <div className="lp-r-shadow" />
    </div>
    {!reduced && <button type="button" className="lp-motion" onClick={() => setPaused(v => !v)} aria-pressed={paused}
      aria-label={paused ? "Play the logo's motion" : "Pause the logo's motion"}>
      <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">{paused ? <path d="M2 1 L9 5 L2 9 Z" fill="currentColor" /> : <><rect x="2" y="1" width="2" height="8" fill="currentColor" /><rect x="6" y="1" width="2" height="8" fill="currentColor" /></>}</svg>
      <span className="lp-motion-t">{paused ? "Play motion" : "Pause motion"}</span>
    </button>}
  </div>;
}

const FAQ = [
  ["What is Reflex?", "A scanner for Hyperliquid perps: each coin's regime, its entry checks and what profitable and large traders hold, in one read."],
  ["Where does the data come from?", "Hyperliquid prices and the positions of profitable and large wallets, read through the day. The engine scores each 4-hour and daily close."],
  ["How do I get access?", "By invitation, with an access code."],
];

export function Landing() {
  // The landing is always dark: reset what a light-mode session in the app may have left,
  // before the first render.
  useState(() => applyTheme("dark"));
  useEffect(() => { document.title = TITLE; }, []);
  const { width } = useViewport();
  const phone = width < 700;
  const [reduced] = useState(reducedMotion);
  const state = useLandingData();
  const data = state?.body || null;
  const focus = data?.coins?.find(c => c.coin === data.focus) || null;
  return <div className="lp" style={DARK_VARS}>
    <a href="#main" className="lp-skip">Skip to content</a>
    <Nav />
    <main id="main">
      <section className="lp-hero lp-width" aria-labelledby="lp-h1">
        <div className="lp-hero-copy">
          <h1 id="lp-h1">One read of where <span>the market is.</span></h1>
          <p>Regime, entry checks and profitable-trader positioning for every Hyperliquid perp.</p>
          <a className="lp-cta" href={ACCESS}>Open Reflex</a>
        </div>
        <HeroArt reduced={reduced} />
      </section>
      <section className="lp-width lp-hero-radar-wrap" aria-label="The Radar at the latest daily close">
        <HeroRadar data={data} phone={phone} />
      </section>
      <Coverage asOf={data?.as_of} />
      <FoldDiagram data={data} focus={focus} reduced={reduced} phone={phone} />

      <Layer id="radar" kicker="Radar" title="Stretch and money on one map." line="Every perp by how stretched it is and how profitable traders lean, at each daily close."
        info={{ title: "Reading the Radar", body: <><p>Across: the engine's z-score, how far price sits from its own recent average. Up: profitable Hyperliquid traders net long.</p><p>Bubble size: the dollars they hold. Ring: distance to the weekly band. The Early setups box: a little stretch and a few traders in.</p></> }}>
        <RadarCrop />
      </Layer>
      <Layer id="engine" kicker="Engine" title="The checks behind every signal." line="The engine names the regime, then tests the entry against its rules."
        info={{ title: "The engine", body: <><p>The Reflexive Crypto Cycle Engine classifies each coin's regime from price deviation and trend energy.</p><p>An entry signal needs its checks: regime, stretch, heat, funding, market breadth and the tracked wallets. What fails is listed as it is. The row is {data?.focus || "the followed coin"} at the latest daily close.</p></> }}>
        <EngineRow row={data?.read} phone={phone} />
      </Layer>
      <Layer id="traders" kicker="Traders" title="What profitable traders hold, and where." line="Their fills on the chart, their size and entry beside the price."
        info={{ title: "The traders", body: <><p>Wallets that have been profitable on Hyperliquid, and large ones, read through the day.</p><p>Names are codenames drawn from the address.</p></> }}>
        <TraderShots />
      </Layer>

      <section className="lp-coin lp-width" aria-labelledby="lp-coin-h">
        <h2 id="lp-coin-h">Every layer on one coin.</h2>
        <figure className="lp-shot lp-shot-wide"><img src={`${IMG}coin-top.webp`} width="1392" height="714" alt="The HYPE coin page: regime, signal, traders' entries on the chart" loading="lazy" /></figure>
      </section>

      <section className="lp-history lp-width" id="history" aria-labelledby="lp-hist-h">
        <div className="lp-section-head">
          <h2 id="lp-hist-h">Today, against every day since 2021. <Info title="Breadth and runs"><p>Each day, the share of scanned coins the engine calls Uptrend; shaded, the risk-on runs, when breadth held above the threshold (dashed).</p><p>A description of what happened, not a signal.</p></Info></h2>
        </div>
        {data?.history ? <HistoryChart history={data.history} /> : <div className="lp-hist lp-hist-empty" />}
      </section>

      <section className="lp-tg lp-width" aria-labelledby="lp-tg-h">
        <div className="lp-tg-copy">
          <h2 id="lp-tg-h">A morning brief in Telegram.</h2>
          <p>Breadth, the early setups and your watched coins, each morning, your time.</p>
        </div>
        <Phone />
      </section>

      <section className="lp-method lp-width" aria-labelledby="lp-method-h">
        <h2 id="lp-method-h">Rules first. <span>Results after.</span></h2>
        <ForwardCounter f={data?.forward} />
      </section>

      <section className="lp-access lp-width" id="access" aria-labelledby="lp-access-h">
        <h2 id="lp-access-h">Access by invitation.</h2>
        <p>Reflex is invitation-only for now. With an access code, you are in.</p>
        <a className="lp-cta" href={ACCESS}>Enter access code</a>
      </section>

      <section className="lp-token lp-width" aria-labelledby="lp-token-h">
        <h3 id="lp-token-h">The Reflex token</h3>
        <p>Proposed: holding the Reflex token as a way in. Nothing about it is decided.</p>
      </section>

      <section className="lp-faq lp-width" aria-label="Questions">
        {FAQ.map(([q, a]) => <details key={q}><summary>{q}<span aria-hidden="true">+</span></summary><p>{a}</p></details>)}
      </section>

      <section className="lp-final lp-width" aria-labelledby="lp-final-h">
        <div className="lp-final-mark" aria-hidden="true"><Mark size={64} /></div>
        <h2 id="lp-final-h">One read. Every morning.</h2>
        <a className="lp-cta" href={ACCESS}>Open Reflex</a>
      </section>
    </main>
    <footer className="lp-footer lp-width">
      <a className="lp-brand" href="/" aria-label="Reflex home"><Mark size={26} /><LogoLettering /></a>
      <span>Market data and positioning for research. Not investment advice.</span>
    </footer>
  </div>;
}
