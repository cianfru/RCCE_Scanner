import { useEffect, useRef, useState, type ReactNode } from 'react';
import { MotionConfig, motion, useInView, useReducedMotion } from 'framer-motion';
import { ArrowRight, ArrowUpRight, Check, CandlestickChart, Clock3, Menu, Minus, Pause, Play, X } from 'lucide-react';
import LogoSculpture from './LogoSculpture.jsx';
import LiveScannerPreview from './LiveScannerPreview.jsx';
import { Mark, LogoLettering } from './Mark';
import TokenLogo from '../components/TokenLogo.jsx';
import './base.css';
import './palette.css';
import './refined-landing.css';

function Action({ href, children, secondary = false, liquid = false }: { href: string; children: ReactNode; secondary?: boolean; liquid?: boolean }) {
  const reduced = useReducedMotion();
  return <motion.a href={href} className={`rx-action${secondary ? ' rx-action-secondary' : ''}${liquid ? ' rx-action-liquid' : ''}`}
    whileHover={reduced || liquid ? undefined : { scale: 1.02 }} whileTap={reduced ? undefined : { scale: .98 }}>
    <span className="rx-action-label">{children}</span><span className="rx-action-icon"><ArrowUpRight size={18} /></span>
    {liquid && <span className="rx-action-surface" aria-hidden="true"><i /><i /></span>}
  </motion.a>;
}

function LiquidFilter() {
  return <svg className="rx-action-filters" aria-hidden="true" focusable="false"><defs>
    <filter id="reflex-cta-liquid" x="-20%" y="-50%" width="150%" height="200%" colorInterpolationFilters="sRGB">
      <feGaussianBlur in="SourceGraphic" stdDeviation="3" result="blur" />
      <feColorMatrix in="blur" mode="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 20 -10" result="liquid" />
      <feBlend in="SourceGraphic" in2="liquid" />
    </filter>
  </defs></svg>;
}

function Wordmark() {
  return <a href="/" className="rx-brand" aria-label="Reflex home"><Mark size={37} /><LogoLettering /></a>;
}

const navigation = [['Platform', '#platform'], ['The engine', '#engine'], ['Access', '#access'], ['FAQ', '#faq']];

function Header() {
  const [open, setOpen] = useState(false);
  const toggle = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setOpen(false); toggle.current?.focus(); }
    };
    document.addEventListener('keydown', close);
    return () => document.removeEventListener('keydown', close);
  }, [open]);
  return <header className="rx-header">
    <div className="rx-nav rx-width">
      <Wordmark />
      <nav className="rx-desktop-nav" aria-label="Main navigation">{navigation.map(([label, href]) => <a key={href} href={href}>{label}</a>)}</nav>
      <a href="/scanner" className="rx-enter">Enter app <ArrowUpRight size={17} /></a>
      <button ref={toggle} className="rx-menu-toggle" aria-label={open ? 'Close menu' : 'Open menu'} aria-expanded={open} aria-controls="mobile-navigation" onClick={() => setOpen(!open)}>{open ? <X size={22} /> : <Menu size={22} />}</button>
    </div>
    <nav id="mobile-navigation" className="rx-mobile-nav" aria-label="Mobile navigation" hidden={!open}>
      {navigation.map(([label, href]) => <a key={href} href={href} onClick={() => setOpen(false)}>{label}<ArrowUpRight size={16} /></a>)}
    </nav>
  </header>;
}

function Hero() {
  const hero = useRef<HTMLElement>(null);
  const inView = useInView(hero, { amount: .1 });
  const reduced = useReducedMotion();
  const [paused, setPaused] = useState(false);
  const [visible, setVisible] = useState(true);
  useEffect(() => {
    const update = () => setVisible(!document.hidden);
    update();
    document.addEventListener('visibilitychange', update);
    return () => {
      document.removeEventListener('visibilitychange', update);
    };
  }, []);
  return <section className="rx-hero" ref={hero}>
    <div className="rx-hero-grid" aria-hidden="true" />
    <div className="rx-hero-main rx-width">
      <div className="rx-hero-content">
        <p className="rx-eyebrow">Market intelligence for Hyperliquid</p>
        <h1>Price is only<br /><span>part of the story.</span></h1>
        <p className="rx-hero-description">Market cycles. Signals. Onchain positioning.<br className="rx-desktop-break" /> A clearer view of what’s behind the move.</p>
        <div className="rx-hero-actions"><Action href="/scanner" liquid>Explore Reflex</Action></div>
      </div>
      <div className="rx-hero-visual">
        <div className="rx-hero-art" aria-hidden="true"><LogoSculpture active={inView && !reduced && !paused && visible} /></div>
        {!reduced && <button className="rx-motion" onClick={() => setPaused(!paused)} aria-label={paused ? 'Play logo animation' : 'Pause logo animation'} aria-pressed={paused}>{paused ? <Play size={12} /> : <Pause size={12} />}<span>{paused ? 'Play motion' : 'Pause motion'}</span></button>}
      </div>
    </div>
    <div className="rx-capabilities rx-width" aria-label="Platform capabilities">
      <span>One connected view</span><div><CandlestickChart size={21} strokeWidth={1.5} aria-hidden="true" /> Market regimes</div><div><Clock3 size={21} strokeWidth={1.5} aria-hidden="true" /> Timeframe alignment</div><div><Mark size={21} /> Hyperliquid intelligence</div>
    </div>
  </section>;
}

// These miniatures explain the product; only LiveScannerPreview fetches live data.
const scannerExamples = [
  { coin: 'BTC', regime: 'Uptrend', color: 'mint', signal: 'Wait' },
  { coin: 'ETH', regime: 'Accumulation', color: 'blue', signal: 'Wait' },
  { coin: 'SOL', regime: 'Uptrend', color: 'mint', signal: 'Wait' },
];

function TraderPositioning() {
  const [cohort, setCohort] = useState('All traders');
  const exampleSplits: Record<string, number[]> = { 'All traders': [64, 42, 71], 'Profitable traders': [58, 55, 63] };
  return <div className="rx-mini-position">
    <div className="rx-mini-label"><span>Trader positioning</span><span>Long / short wallets</span></div>
    <div className="rx-cohort-switch" role="group" aria-label="Example trader cohort">
      {Object.keys(exampleSplits).map(label => <button key={label} aria-pressed={cohort === label} onClick={() => setCohort(label)}>{label}</button>)}
    </div>
    <div className="rx-trader-rows" aria-live="polite">
      {scannerExamples.map(({ coin }, index) => {
        const long = exampleSplits[cohort][index];
        return <div className="rx-trader-row" key={coin}>
          <span className="rx-mini-coin"><TokenLogo symbol={`${coin}/USDT`} size={19} />{coin}</span>
          <div className="rx-trader-split" role="img" aria-label={`${coin}: ${long}% long wallets, ${100 - long}% short wallets. Illustrative data.`}>
            <span className="rx-trader-values"><span>{long}%</span><span>{100 - long}%</span></span>
            <span className="rx-trader-bar"><i style={{ width: `${long}%` }} /><i style={{ width: `${100 - long}%` }} /></span>
          </div>
        </div>;
      })}
    </div>
    <div className="rx-trader-key"><span><i /> Long wallets</span><span><i /> Short wallets</span></div>
  </div>;
}

function ProductVisual({ type }: { type: 'scanner' | 'cycle' | 'positioning' }) {
  if (type === 'scanner') return <div className="rx-mini-markets">
    <div className="rx-mini-label"><span>Scanner watchlist</span><span>Daily · 1D</span></div>
    <table className="rx-mini-table" aria-label="Illustrative scanner watchlist">
      <thead><tr><th scope="col">Market</th><th scope="col">Regime</th><th scope="col">Signal</th></tr></thead>
      <tbody>{scannerExamples.map(({ coin, regime, color, signal }) => <tr key={coin}>
        <th scope="row"><span className="rx-mini-coin"><TokenLogo symbol={`${coin}/USDT`} size={22} />{coin}</span></th>
        <td><span className={`rx-chip ${color}`}>{regime}</span></td><td><span className="rx-mini-signal">{signal}</span></td>
      </tr>)}</tbody>
    </table>
  </div>;
  if (type === 'cycle') return <div className="rx-mini-cycle" aria-hidden="true"><div className="rx-mini-label"><span>Price + trend energy</span><span>4H · 1D</span></div><svg viewBox="0 0 320 122"><path className="rx-chart-grid" d="M0 30H320M0 70H320M0 110H320" /><path d="M0 102 C22 105 30 87 46 89 S65 109 86 76 S108 94 128 55 S151 68 170 31 S193 64 211 43 S238 10 258 29 S283 15 320 8" fill="none" stroke="#97FCE4" strokeWidth="2" /><path d="M0 109 C55 110 84 94 120 80 S184 48 224 37 S287 22 320 17" fill="none" stroke="#648b86" strokeDasharray="4 5" /></svg><span className="rx-chart-key"><i /> Price <i /> Baseline</span></div>;
  return <TraderPositioning />;
}

function Platform() {
  return <section id="platform" className="rx-section rx-products">
    <div className="rx-width">
      <div className="rx-section-heading rx-centered"><p className="rx-eyebrow">The Reflex platform</p><h2>Connect the dots.<br />See the whole setup.</h2><p>From the market’s direction to the positions behind it.<br className="rx-desktop-break" /> Three perspectives, brought into one research workspace.</p></div>
      <div className="rx-product-grid">
        {[
          { type: 'scanner' as const, name: 'Market Scanner', description: 'Find the markets worth a closer look. Compare regimes and signal conditions across the watchlist.', href: '#preview', link: 'See the scanner' },
          { type: 'cycle' as const, name: 'Cycle Engine', description: 'Put each move in context. Read price deviation and trend energy across the four-hour and daily timeframes.', href: '#engine', link: 'Explore the engine' },
          { type: 'positioning' as const, name: 'Hyperlens', description: 'See how traders are positioned. Compare long and short wallets across all traders and profitable traders on Hyperliquid.', href: '/hyperlens', link: 'Explore Hyperlens' },
        ].map(product => <article className="rx-product" key={product.type}><ProductVisual type={product.type} /><span className="rx-example-label">Illustrative view</span><h3>{product.name}</h3><p>{product.description}</p><a href={product.href} className="rx-text-link">{product.link}<ArrowUpRight size={16} /></a></article>)}
      </div>
      <div className="rx-product-foot"><span>Built for research. Designed to keep you in control.</span><a href="/scanner">Open the platform <ArrowRight size={16} /></a></div>
    </div>
  </section>;
}

function Scanner() {
  return <section id="preview" className="rx-section rx-preview"><div className="rx-width">
    <div className="rx-section-heading rx-split-heading"><div><p className="rx-eyebrow">Inside Reflex</p><h2>The market,<br />in perspective.</h2></div><p>Go from a broad view to an individual setup. The preview below uses the same scanner feed as the terminal.</p></div>
    <LiveScannerPreview />
  </div></section>;
}

function Comparison() {
  const rows = [
    ['Open charts one at a time', 'Scan market regimes in one view'],
    ['Switch between timeframes', 'Compare four-hour and daily conditions'],
    ['Read price in isolation', 'Add cycle and positioning context'],
    ['Follow a signal without the detail', 'Inspect its conditions and counter-evidence'],
  ];
  return <section className="rx-section rx-comparison"><div className="rx-width">
    <div className="rx-section-heading rx-centered"><h2>Less chart-hopping.<br />More context.</h2><p>Spend less time assembling the picture.<br className="rx-desktop-break" /> Spend more time understanding it.</p></div>
    <div className="rx-compare-table" role="table" aria-label="Research workflows compared">
      <div className="rx-compare-head" role="row"><div role="columnheader">A fragmented workflow</div><div role="columnheader"><Mark size={26} /> With Reflex</div></div>
      {rows.map(([before, after]) => <div className="rx-compare-row" role="row" key={before}><div role="cell"><Minus size={16} />{before}</div><div role="cell"><Check size={17} />{after}</div></div>)}
    </div>
  </div></section>;
}

const cycleStages = [
  { name: 'Accumulation', x: 76, y: 166, description: 'Price is close to its baseline and directional energy is limited. Watch for evidence of a shift; a quiet market alone does not establish a reversal.' },
  { name: 'Uptrend', x: 188, y: 94, description: 'Price and trend energy are moving higher together. Compare the four-hour move with the daily regime to see whether the timeframes agree.' },
  { name: 'Overheated', x: 306, y: 34, description: 'Price is unusually extended above its baseline. Momentum may continue, but the distance from the mean deserves closer attention.' },
  { name: 'Downtrend', x: 445, y: 135, description: 'Price and trend energy point lower. Look for a change in the underlying conditions before changing your interpretation.' },
  { name: 'Capitulation', x: 556, y: 192, description: 'Price is depressed and directional energy is strongly negative. An extreme reading alone is not evidence of a bottom.' },
];

function CycleExplorer() {
  const [selected, setSelected] = useState(1);
  const current = cycleStages[selected];
  return <section className="rx-section rx-engine" id="engine"><div className="rx-width rx-engine-layout">
    <div className="rx-engine-copy"><p className="rx-eyebrow">The cycle engine</p><h2>Every move<br />has a context.</h2><p>Price tells you where a market is. The Reflexive Crypto Cycle Engine helps describe the conditions around it.</p><p>Explore five phases of a conceptual cycle, then compare them with the regimes in the terminal.</p><a href="/scanner" className="rx-text-link">Explore market regimes <ArrowUpRight size={16} /></a></div>
    <div className="rx-cycle-panel">
      <div className="rx-cycle-top"><span>A market cycle</span><span className="rx-chip mint">{current.name}</span></div>
      <svg className="rx-cycle-chart" viewBox="0 0 640 230" role="img" aria-label={`Illustrative market cycle, highlighting ${current.name}`}>
        <defs><linearGradient id="rx-cycle-area" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#97FCE4" stopOpacity=".16" /><stop offset="1" stopColor="#97FCE4" stopOpacity="0" /></linearGradient></defs>
        <path className="rx-chart-grid" d="M16 50H624M16 100H624M16 150H624M16 200H624" />
        <path d="M16 175 C46 175 56 163 76 166 S120 178 153 126 S176 112 188 94 S261 15 306 34 S355 64 384 72 S422 106 445 135 S520 212 556 192 S598 168 624 172 V225 H16Z" fill="url(#rx-cycle-area)" />
        <path d="M16 175 C46 175 56 163 76 166 S120 178 153 126 S176 112 188 94 S261 15 306 34 S355 64 384 72 S422 106 445 135 S520 212 556 192 S598 168 624 172" stroke="#97FCE4" strokeWidth="2" fill="none" />
        <line x1={current.x} x2={current.x} y1={current.y} y2="225" stroke="#97FCE466" strokeDasharray="3 5" />
        {cycleStages.map((stage, index) => <circle key={stage.name} cx={stage.x} cy={stage.y} r={index === selected ? 5 : 3} fill={index === selected ? '#97FCE4' : '#526f69'} />)}
        <circle cx={current.x} cy={current.y} r="13" fill="#97FCE410" stroke="#97FCE455" />
      </svg>
      <div className="rx-cycle-controls" role="group" aria-label="Explore market cycle phases">{cycleStages.map((stage, index) => <button key={stage.name} aria-pressed={selected === index} onClick={() => setSelected(index)}>{stage.name}</button>)}</div>
      <div className="rx-cycle-description" aria-live="polite"><h3>{current.name}</h3><p>{current.description}</p></div>
      <p className="rx-chart-note">Conceptual illustration, not a forecast. The terminal also identifies other regimes.</p>
    </div>
  </div></section>;
}

function Workflow() {
  return <section className="rx-section rx-workflow" id="workflow"><div className="rx-width">
    <div className="rx-section-heading rx-centered"><h2>From a signal<br />to your own view.</h2><p>A research workflow that keeps the decision with you.</p></div>
    <div className="rx-steps">{[
      ['01', 'Scan the market', 'Start with the watchlist. Find the regimes and signal conditions that deserve your attention.'],
      ['02', 'Follow the evidence', 'Compare timeframes, review the conditions, and inspect the positioning around the setup.'],
      ['03', 'Make your own call', 'Weigh the evidence against your strategy, research, and risk limits before deciding.'],
    ].map(([number, title, description]) => <article key={number}><span className="rx-step-number">{number}</span><h3>{title}</h3><p>{description}</p></article>)}</div>
  </div></section>;
}

const questions = [
  ['What does Reflex do?', 'Reflex brings market regimes, signal conditions, and Hyperliquid intelligence into one research workspace. Its cycle engine uses price deviation and trend energy to classify market conditions.'],
  ['Where does the scanner preview get its data?', 'It reads the same public scanner API as the terminal and refreshes every minute. If the feed is unavailable, the preview says so. The small product graphics and cycle diagram are illustrative.'],
  ['Can I use Reflex today?', 'Reflex is currently a private product preview. The app requires an access code while the product is being refined.'],
  ['How will token access work?', 'The proposed model is to hold a minimum eligible token balance in your own wallet and verify ownership. The threshold, supported balances, and access terms will be published before launch.'],
  ['Will I need to stake or spend tokens?', 'The proposed access model does not require staking, depositing, or spending tokens. Wallet verification is intended to prove ownership, with access based on your eligible balance.'],
  ['Does a signal tell me what to trade?', 'No. A regime describes conditions, and a signal summarises the engine’s checks. Neither guarantees an outcome. Use them alongside your own research and risk limits.'],
];

function AccessAndFAQ() {
  return <>
    <section className="rx-section rx-access" id="access"><div className="rx-width rx-access-layout">
      <div><p className="rx-eyebrow">Platform access</p><h2>Research now.<br />Know what’s next.</h2><p>Reflex is in a password-protected preview while we refine the product. Future access details will be published before launch.</p><Action href="/scanner">Open the scanner</Action></div>
      <div className="rx-access-stages">
        <article><span className="rx-status rx-status-now">Private preview</span><h3>The Reflex scanner</h3><p>Explore market regimes, signal conditions, and individual setups with your access code.</p><Check size={22} /></article>
        <article><span className="rx-status">Proposed model</span><h3>Your wallet. Your access.</h3><p>Hold the required balance to unlock the platform. No staking or spending proposed.</p><span className="rx-access-note">Token details, minimum balance, and terms: to be announced.</span></article>
      </div>
    </div></section>
    <section className="rx-section rx-faq" id="faq"><div className="rx-width rx-faq-layout">
      <div><p className="rx-eyebrow">A little more context</p><h2>Good questions.<br />Clear answers.</h2><a href="https://github.com/cianfru/RCCE_Scanner" className="rx-text-link">Explore the source <ArrowUpRight size={16} /></a></div>
      <div className="rx-faq-list">{questions.map(([question, answer]) => <details key={question}><summary>{question}<span className="rx-faq-icon" aria-hidden="true">+</span></summary><p>{answer}</p></details>)}</div>
    </div></section>
  </>;
}

function Footer() {
  return <>
    <section className="rx-final"><div className="rx-width"><Mark size={54} /><h2>See what’s<br />behind the move.</h2><p>The next perspective is yours.</p><Action href="/scanner" liquid>Explore Reflex</Action></div></section>
    <footer className="rx-footer rx-width"><div className="rx-footer-main"><div><Wordmark /><p>Market intelligence.<br />Independent thinking.</p></div><nav aria-label="Footer navigation"><div><span>Explore</span><a href="#platform">Platform</a><a href="#engine">The engine</a><a href="/hyperlens">Hyperlens</a></div><div><span>Learn more</span><a href="#access">Access</a><a href="#faq">FAQ</a><a href="https://github.com/cianfru/RCCE_Scanner">GitHub <ArrowUpRight size={13} /></a></div></nav></div><div className="rx-footer-bottom"><span>© {new Date().getFullYear()} Reflex</span><span>Research tools. Not investment advice.</span><a href="#main">Back to top ↑</a></div></footer>
  </>;
}

export function RefinedLanding() {
  return <MotionConfig reducedMotion="user"><div className="refined"><LiquidFilter /><a href="#main" className="skip">Skip to content</a><Header /><main id="main"><Hero /><Platform /><Scanner /><Comparison /><CycleExplorer /><Workflow /><AccessAndFAQ /></main><Footer /></div></MotionConfig>;
}
