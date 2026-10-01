// Everything under the first screen of the landing, loaded after it (Landing.jsx).
// Order: Engine, Radar, Traders (the three layers), the diagram that joins them, then the coin
// page, history, the morning brief, the method, access, the token note, FAQ and the last call.
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import RadarMap from "../components/radar/RadarMap.jsx";
import Tabs from "../components/Tabs.jsx";
import HelpTip from "../components/HelpTip.jsx";
import DataTable from "../components/DataTable.jsx";
import { Mark } from "./Mark";
import { SIDES, visible } from "../utils/setupMap.js";
import { bandInfo, moneyMode } from "../utils/radarDepth.js";
import { friendlyReason } from "../utils/signalPresentation.js";
import { themeVars, REGIME_META } from "../theme.js";
import { SCANNER_COLUMNS } from "../scannerColumns.js";
import useViewport from "../hooks/useViewport.js";
import useLandingData from "./useLandingData.js";
import FoldDiagram from "./FoldDiagram.jsx";
import HistoryChart from "./HistoryChart.jsx";
import "../terminal.css";

const DARK_VARS = themeVars("dark");
const IMG = "/landing/";
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const dayLabel = sec => { const d = new Date(sec * 1000); return `${WEEKDAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`; };
const lastDailyClose = sec => Math.floor(sec / 86400) * 86400;
const reducedMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
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

// The live map with numbered marks. The marks are placed on what the map has drawn (the
// followed coin's bubble, the Early setups box, a coin with a weekly-band ring, the stretched
// zone), read from the map's own SVG after each layout.
function RadarLive({ data, phone }) {
  const host = useRef(null);
  const [marks, setMarks] = useState([]);
  const focus = data?.focus;
  const ringCoin = useMemo(() => {
    const coins = (data?.coins || []).filter(c => c.coin !== focus && c.money?.gross_usd > 0);
    const withRing = coins.filter(c => { const b = bandInfo(c.band, c.price); return b.tone !== "none" && b.fill >= 0.35; });
    return withRing.sort((a, b) => b.money.gross_usd - a.money.gross_usd)[0]?.coin || null;
  }, [data, focus]);
  const words = [
    `${focus || "The followed coin"}: profitable traders long; bubble size is the money they hold`,
    "Early setups: little stretch, a few traders in",
    "Ring: how far price is from its weekly band",
    "Stretched: far above its own average",
  ];
  useLayoutEffect(() => {
    const el = host.current;
    if (!el || !data) return undefined;
    let frame = 0;
    const place = () => {
      frame = 0;
      const base = el.getBoundingClientRect();
      const at = (node, fx = 0.5, fy = 0.5) => {
        if (!node) return null;
        const r = node.getBoundingClientRect();
        if (!r.width && !r.height) return null;
        return { x: r.left - base.left + r.width * fx, y: r.top - base.top + r.height * fy };
      };
      const dot = coin => el.querySelector(`.smap-dot[data-coin="${coin}"] .smap-core`);
      const pts = [
        at(dot(focus), 1.05, 1.05),
        at(el.querySelector("svg .smap-box"), 0, 1),
        ringCoin ? at(dot(ringCoin), 1.02, 1.02) : null,
        at(el.querySelector("svg .smap-late"), 0.6, 0.9),
      ];
      // Kept inside the drawn map, clear of its edge.
      const svg = el.querySelector(".smap-mapbox svg")?.getBoundingClientRect();
      const box = svg && { l: svg.left - base.left + 14, r: svg.right - base.left - 14, t: svg.top - base.top + 14, b: svg.bottom - base.top - 14 };
      setMarks(pts.map(p => (p && box ? { x: Math.min(box.r, Math.max(box.l, p.x)), y: Math.min(box.b, Math.max(box.t, p.y)) } : p)));
    };
    const later = () => { if (!frame) frame = requestAnimationFrame(place); };
    const t = setTimeout(later, 60);
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(later) : null;
    ro?.observe(el);
    return () => { clearTimeout(t); cancelAnimationFrame(frame); ro?.disconnect(); };
  }, [data, focus, ringCoin, phone]);
  return <figure className="lp-callouts lp-radar-live">
    <div className="lp-radar-host" ref={host}>
      <HeroRadar data={data} phone={phone} />
      {marks.map((m, i) => m && <span key={i} className="lp-mark" style={{ left: m.x, top: m.y }}>{i + 1}</span>)}
    </div>
    <ol className="lp-mark-list">{words.map((t, i) => (marks[i] ? <li key={i}><span className="lp-mark">{i + 1}</span>{t}</li> : null))}</ol>
  </figure>;
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

const FAQ = [
  ["What is Reflex?", "A scanner for Hyperliquid perps: each coin's regime, its entry checks and what profitable and large traders hold, in one read."],
  ["Where does the data come from?", "Hyperliquid prices and the positions of profitable and large wallets, read through the day. The engine scores each 4-hour and daily close."],
  ["How do I get access?", "By invitation, with an access code."],
];

export default function Sections() {
  const { width } = useViewport();
  const phone = width < 700;
  const [reduced] = useState(reducedMotion);
  const state = useLandingData();
  const data = state?.body || null;
  const focus = data?.coins?.find(c => c.coin === data.focus) || null;
  return <>
      <Layer id="engine" kicker="Engine" title="The checks behind every signal." line="The engine names the regime, then tests the entry against its rules."
        info={{ title: "The engine", body: <><p>The Reflexive Crypto Cycle Engine classifies each coin's regime from price deviation and trend energy.</p><p>An entry signal needs its checks: regime, stretch, heat, funding, market breadth and the tracked wallets. What fails is listed as it is. The row is {data?.focus || "the followed coin"} at the latest daily close.</p></> }}>
        <EngineRow row={data?.read} phone={phone} />
      </Layer>
      <Layer id="radar" kicker="Radar" title="Stretch and money on one map." line="Every perp by how stretched it is and how profitable traders lean. Switch sides: Long, Short or Both."
        info={{ title: "Reading the Radar", body: <><p>Across: the engine's z-score, how far price sits from its own recent average. Up: profitable Hyperliquid traders net long.</p><p>Bubble size: the dollars they hold. Ring: distance to the weekly band. The Early setups box: a little stretch and a few traders in.</p></> }}>
        <RadarLive data={data} phone={phone} />
      </Layer>
      <Layer id="traders" kicker="Traders" title="What profitable traders hold, and where." line="Their fills on the chart, their size and entry beside the price."
        info={{ title: "The traders", body: <><p>Wallets that have been profitable on Hyperliquid, and large ones, read through the day.</p><p>Names are codenames drawn from the address.</p></> }}>
        <TraderShots />
      </Layer>
      <FoldDiagram data={data} focus={focus} reduced={reduced} phone={phone} />

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
  </>;
}
