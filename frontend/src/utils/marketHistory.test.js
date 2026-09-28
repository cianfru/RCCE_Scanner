import test from 'node:test';
import assert from 'node:assert/strict';
import {
  COPY, RANGES, altTicks, bandDistance, bandHead, bandOn, bandShort, breadthContext, btcSide, countWords, dayDate, episodesOf,
  fanGeometry, fanMedian, fgSplit, inRange, logTicks, ordinal, percentileOf, popWords, readoutCells, rowsOf, runsMarks,
  signedPct, stripCounts, visibleTexts, visibleWords,
} from './marketHistory.js';

const FORBIDDEN = /\b(will|expect\w*|likely|predict\w*|forecast\w*|probab\w*|odds|target\w*)\b/i;
const K = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60];

const data = {
  columns: ['day', 'n', 'uptrend'], days: [[100, 50, 0.2], [300, 50, 0.5], [500, 50, 0.8]],
  episode_columns: ['start', 'end', 'breadth', 'btc10', 'alt10', 'btc30', 'alt30', 'btc60', 'alt60'],
};

// A fan like today's: 3 episodes, uptrend and BTC in paths mode, the alt in bands mode.
function makeFan(over = {}) {
  const path = (a, step) => K.map((k, i) => +(a + step * i).toFixed(3));
  const band = (mid, w) => K.map((k, i) => [mid - 2 * w * i, mid - w * i, mid, mid + w * i, mid + 2 * w * i]);
  return {
    day: 1000, state: 'on', rule: { width: 0.05, btc_side: 'holding', step: 0 }, runs: 8, min_runs: 6, too_few: false,
    k: K, q: [0.1, 0.25, 0.5, 0.75, 0.9],
    episodes: [[900, 880, 100, 0], [920, 880, 100, 1], [950, 940, 110, 0]],
    paths: { uptrend: [path(0.82, -0.03), path(0.82, 0.01), path(0.82, -0.06)],
      btc: [path(84000, -500), path(84000, 800), path(84000, 100)], alt: [path(0, -2), path(0, 1), path(0, -4)] },
    bands: { uptrend: band(0.8, 0.02), btc: band(84000, 400), alt: band(-3, 1.5) },
    ordinary: { btc: path(84000, 50), alt: path(0, -1.1) },
    show: { uptrend: 'paths', btc: 'paths', alt: 'bands' },
    check: { scored: 52, tested: 82, series: { uptrend: { pass: false }, btc: { pass: false }, alt: { pass: true } }, median_vs_all: 1.13 },
    live_check: null,
    ...over,
  };
}

// A payload like today's, for the word budget and the rendered-copy checks.
function makePayload(over = {}) {
  const ep = (start, alt30, extra = {}) => [start, start + 3, 0.75, 1, 1, 2, alt30, 3, alt30 - 5, extra];
  const bands = [[0, 0.25, 'under 25%'], [0.25, 0.4, '25-40%'], [0.4, 0.55, '40-55%'], [0.55, 0.7, '55-70%'], [0.7, 0.85, '70-85%'], [0.85, 1.01, '85% and over']]
    .map(([lo, hi, label]) => ({ label, lo, hi, verdict: { episodes: 18, alt: { above_base: 9, direction: 'mixed' }, btc: { above_base: 10, direction: 'mixed' } },
      episodes: Array.from({ length: 18 }, (_, i) => ep(200 + 20 * i, i % 2 ? 3 : -20).slice(0, 9)),
      later: [ep(700, 10).slice(0, 9), ep(760, -1).slice(0, 9), ep(820, -2).slice(0, 9), [990, 1000, 0.72, 2.9, -1, null, null, null, null]] }));
  return {
    columns: ['day', 'n', 'uptrend', 'overheated', 'downtrend', 'basing', 'median_z', 'btc'],
    days: Array.from({ length: 200 }, (_, i) => [801 + i, 145, 0.8, 0, 0.1, 0.1, 1.2, 80000 + 20 * i]),
    episode_columns: data.episode_columns, end_day: 600, coins: 151, scored_through: 1000,
    base: { 30: { btc: { median: 0.3 }, alt: { median: -7.4 } }, 60: { btc: { median: 1.2 }, alt: { median: -13.1 } } },
    base_period: [100, 600], bands,
    today: { day: 1000, uptrend: 0.8207, overheated: 0, percentile: 77, band: '70-85%', since: 100 },
    cycle: { type: 'on', start: 962, day: 39, threshold: 0.55, off_days: 5, below_days: 0, past: 12, median: 47, reached: 7, more: 30, lasted_more: 5,
      runs: [[100, 41, 0.84], [150, 11, 0.71], [170, 8, 0.65], [200, 19, 0.65], [260, 143, 0.98], [420, 53, 0.86], [500, 101, 0.97],
        [620, 30, 0.79], [700, 119, 0.98], [830, 6, 0.58], [850, 96, 0.98], [950, 148, 0.96]] },
    fear_greed: [[998, 70], [999, 72], [1000, 74]],
    btc_band_weekly: [[986, 70000, 72000], [993, 70253, 72617], [1000, 70366, 73695]],
    forward_test: { declared_day: 999, share: 0.55, episodes: [], history: [[18965, 13, 0.77, -6, -4, -35], [19997, 10, 0.83, 16, -1, 64], [20356, 1, 0.89, 2, -20, -40]] },
    fan: makeFan(),
    ...over,
  };
}

test('rows and ranges', () => {
  const rows = rowsOf(data);
  assert.deepEqual(rows[2], { day: 500, n: 50, uptrend: 0.8 });
  assert.equal(inRange(rows, '1y').length, 2);
  assert.equal(inRange(rows, 'all').length, 3);
  assert.deepEqual(RANGES.map(r => r.key), ['3m', '1y', '3y', 'all']);
  assert.equal(inRange(rows, '3m').length, 1);
});

test('percentile counts days strictly below', () => {
  assert.equal(percentileOf([1, 2, 3, 4], 3), 50);
  assert.equal(percentileOf([], 3), null);
  assert.deepEqual([1, 2, 3, 4, 11, 12, 13, 21, 22, 77, 101, 111].map(ordinal),
    ['1st', '2nd', '3rd', '4th', '11th', '12th', '13th', '21st', '22nd', '77th', '101st', '111th']);
});

test('episodes: newest first, scored once 30 or 60 days have closed', () => {
  const band = { episodes: [[10, 12, 0.7, 1, 2, 3, 4, 5, 6]],
    later: [[40, 41, 0.72, 1, 2, 3, 4, null, null], [70, 71, 0.8, 1, 2, null, null, null, null]] };
  const eps = episodesOf({ ...data, today: { day: 100 }, scored_through: 100 }, band);
  assert.deepEqual(eps.map(e => [e.start, e.due30, e.due60, e.later]), [[70, null, 130, true], [40, null, null, true], [10, null, null, false]]);
  assert.equal(eps[1].alt60, null);                    // closed on day 100 but no data: shown as a dash
  const pending = episodesOf({ ...data, today: { day: 95 } }, band);
  assert.deepEqual(pending.map(e => [e.start, e.due30, e.due60]), [[70, 100, 130], [40, null, 100], [10, null, null]]);
});

test('strip counts leave pending episodes out and compare with ordinary', () => {
  const eps = [{ alt30: 5 }, { alt30: -7.4 }, { alt30: -8 }, { alt30: -2 }, { alt30: null, due30: 120 }, { alt30: 3, due30: 99 }];
  assert.deepEqual(stripCounts(eps, -7.4), { better: 2, worse: 2 });
});

test('BTC band: the day after a Sunday close uses that week; the close day uses the previous one', () => {
  const weekly = [[986, 1, 2], [993, 3, 4], [1000, 5, 6]];
  assert.deepEqual(bandOn(weekly, 994), [3, 4]);
  assert.deepEqual(bandOn(weekly, 993), [1, 2]);
  assert.deepEqual(bandOn(weekly, 1000), [3, 4]);
  assert.deepEqual(bandOn(weekly, 1001), [5, 6]);
  assert.equal(bandOn(weekly, 986), null);
  assert.equal(bandOn(weekly, 1008), null);            // past the last week's reach
  assert.equal(bandOn([], 5), null);
  assert.equal(btcSide(84472, [70254, 72617]), 'above');
  assert.equal(Math.round(bandDistance(84472, [70254, 72617]) * 10) / 10, 16.3);
  assert.equal(btcSide(71000, [70254, 72617]), 'inside');
  assert.equal(bandDistance(71000, [70254, 72617]), 0);
  assert.equal(btcSide(60000, [70254, 72617]), 'below');
  assert.ok(bandDistance(60000, [70254, 72617]) < 0);
});

test('fan geometry: the future zone is 60 of 150 days at 3M; knots sit at T + k; paths series get no bands', () => {
  const fan = makeFan();
  const g = fanGeometry({ fan, T: 1000, d0: 910, width: 712 });
  assert.equal(g.frac, 0.4);
  assert.equal(g.knots.length, 13);
  assert.deepEqual(g.knots.map(k => k.day), K.map(k => 1000 + k));
  assert.equal(g.knots[12].x, 712 - 44);
  assert.equal(g.knots[0].x, g.zone[0]);
  assert.equal(g.polys.uptrend, null);
  assert.equal(g.polys.btc, null);
  assert.equal(g.polys.alt.mid.length, 13);
  assert.deepEqual(g.polys.alt.outer[6].slice(1), fan.bands.alt[6].filter((_, i) => i === 0 || i === 4));
  const noFuture = fanGeometry({ fan: null, T: 1000, d0: 910, width: 712, future: false });
  assert.equal(noFuture.zone, null);
  assert.equal(noFuture.x(1000), 712 - 44);
  const tooFew = fanGeometry({ fan: makeFan({ too_few: true, show: { uptrend: 'paths', btc: 'paths', alt: 'paths' } }), T: 1000, d0: 910, width: 712 });
  assert.equal(tooFew.polys.alt, null);
  assert.equal(fanMedian(makeFan({ too_few: true }), 'alt').length, 0);
  assert.equal(fanMedian(fan, 'uptrend').length, 13);
  // At 1Y the zone is about 14% of the width.
  assert.ok(Math.abs(fanGeometry({ fan, T: 1000, d0: 635, width: 712 }).frac - 0.141) < 0.001);
});

test('readout cells: middle half for bands series, lowest-highest range for paths series', () => {
  const fan = makeFan();
  const alt = readoutCells(fan, 'alt', 6);
  assert.equal(alt.median, '−3.0%');
  assert.equal(alt.spread, '−12/+6');
  const up = readoutCells(fan, 'uptrend', 6);
  assert.equal(up.median, '80%');
  assert.equal(up.spread, 'range 46–88');
  const btc = readoutCells(fan, 'btc', 12);
  assert.equal(btc.median, '$84k');
  assert.equal(btc.spread, 'range 78k–93.6k');
  const few = readoutCells(makeFan({ too_few: true, show: { uptrend: 'paths', btc: 'paths', alt: 'paths' } }), 'alt', 6);
  assert.equal(few.median, null);
  assert.match(few.spread, /^range /);
});

test('runs chart marks: counts at today and 30 days on, "too few" under 6', () => {
  const c = makePayload().cycle;
  const m = runsMarks(c);
  assert.equal(m.now.text, '7 of 12');
  assert.equal(m.later.text, '5 of 7');
  assert.equal(m.later.day, 69);
  assert.equal(m.columns.filter(x => x.reached).length, 7);
  assert.equal(runsMarks({ ...c, reached: 4, lasted_more: 2 }).later.text, '2 of 4, too few');
  assert.equal(runsMarks({ ...c, past: 5, reached: 3 }).now.text, '3 of 5, too few');
  assert.equal(runsMarks({ ...c, reached: 0 }).later, null);
  assert.equal(runsMarks(null), null);
});

test('Fear & Greed split sums to 100', () => {
  const s = fgSplit([10, 40, 41, 55, 69, 70, 90, null]);
  assert.deepEqual(s, [29, 43, 28]);
  assert.equal(s.reduce((a, b) => a + b, 0), 100);
  for (const vs of [[1, 50, 99], [1, 1, 50], [70, 70, 70, 20, 50, 50, 50]]) assert.equal(fgSplit(vs).reduce((a, b) => a + b, 0), 100);
  assert.equal(fgSplit([]), null);
});

test('band labels', () => {
  assert.deepEqual([{ lo: 0, hi: 0.25 }, { lo: 0.7, hi: 0.85 }, { lo: 0.85, hi: 1.01 }].map(bandShort), ['<25', '70–85', '85+']);
  assert.deepEqual([{ lo: 0, hi: 0.25 }, { lo: 0.7, hi: 0.85 }, { lo: 0.85, hi: 1.01 }].map(bandHead), ['under 25%', '70–85%', '85% and over']);
});

// Every string the drawer can show, across the variants a payload can produce.
function allCopy() {
  const out = [];
  const walk = v => {
    if (typeof v === 'string') out.push(v);
    else if (Array.isArray(v)) v.forEach(walk);
    else if (v && typeof v === 'object') Object.values(v).forEach(walk);
  };
  walk(COPY);                                          // the static strings
  const c = COPY;
  const checks = {
    pass: { scored: 52, series: { uptrend: { pass: true }, btc: { pass: true }, alt: { pass: true } }, median_vs_all: 0.8 },
    passFar: { scored: 52, series: { uptrend: { pass: true }, btc: { pass: true }, alt: { pass: true } }, median_vs_all: 1.2 },
    passSame: { scored: 52, series: { uptrend: { pass: true }, btc: { pass: true }, alt: { pass: true } }, median_vs_all: 1.0 },
    someFail: makeFan().check,
    oneFail: { scored: 52, series: { uptrend: { pass: true }, btc: { pass: false }, alt: { pass: true } }, median_vs_all: 1 },
    untested: { untested: true, series: {} },
  };
  const live = { logged: 14, scored: 13, mid: { uptrend: [6, 13], btc: [7, 13], alt: [6, 12] }, out: {} };
  for (const state of ['on', 'off']) for (const side of ['holding', 'below', 'either']) for (const ck of Object.values(checks))
    for (const lv of [null, live, { ...live, scored: 3 }]) for (const tooFew of [false, true]) {
      walk(c.pop.fan({ state, side, since: 'May 2021', width: 5, today: '82%', paths: 12, runs: tooFew ? 4 : 8, tooFew, check: ck, live: lv }));
    }
  walk(c.pop.fanNone({ since: 'May 2021' }));
  walk(c.pop.uptrend({ coins: 151, since: 'May 2021' }));
  walk(c.pop.band());
  walk(c.pop.runs({ on: true, since: 'May 2021' }));
  walk(c.pop.runs({ on: false, since: 'May 2021' }));
  for (const verdict of [{ episodes: 18, alt: { direction: 'mixed', above_base: 9 } }, { episodes: 9, alt: { direction: 'continuation', above_base: 7 } },
    { episodes: 9, alt: { direction: 'pullback', above_base: 1 } }, { episodes: 3, direction: 'too few episodes' }, null]) {
    walk(c.pop.episodes({ alt: '−7.4%', btc: '+0.3%', from: 'May 2021', to: 'Mar 2026', end: '29 Mar 2026', better: 9, n: 18, verdict }));
  }
  walk(c.pop.ft({ declared: '26 Sep 2026', share: 55, base: '−13.1%', bear: 5, n: 8 }));
  walk(c.pop.past({ n: 8, base: '−13.1%' }));
  walk(c.pop.fg({ since: 'Feb 2018' }));
  for (const [p, r, f] of [[12, 8, false], [4, 3, true], [1, 1, false]]) walk(c.caption(p, r, f));
  walk([c.axis.h(30), c.axis.h(60), c.readout.range('3–95'), c.readout.altVs('−6%'), c.kpi.pct(77), c.kpi.day(39), c.kpi.run(true), c.kpi.run(false),
    c.kpi.under(1), c.kpi.under(2), ...['above', 'below', 'inside'].map(c.kpi.band), c.runs.head(true), c.runs.head(false), c.runs.mark(7, 12),
    c.runs.mark(2, 4), c.runs.hover(20280, 96, 0.98), c.episodes.head('70–85%'), c.episodes.count(13, 9), c.episodes.ordinary('−7.4%'),
    c.episodes.all(22), c.episodes.due('23 Oct'), c.episodes.pts(18), c.episodes.pts(-16), c.episodes.ongoing(35), c.episodes.column(20689, 10.4),
    c.episodes.pending(20689), c.ft.scored(0), c.ft.worse(7, 8), c.ft.square(20730, null), c.ft.square(20730, -20)]);
  for (const range of ['3m', '1y']) for (const cyc of [makePayload().cycle, { ...makePayload().cycle, type: 'off', below_days: 0 }, { ...makePayload().cycle, below_days: 2 }])
    for (const fan of [makeFan(), null, makeFan({ too_few: true, runs: 4 })]) walk(visibleTexts('breadth', makePayload({ cycle: cyc, fan }), { range }));
  walk(visibleTexts('fear', makePayload()));
  return out;
}

test('no forecast words, no "Larsson", no emojis in any copy or rendered template', () => {
  const strings = allCopy();
  assert.ok(strings.length > 200);
  for (const s of strings) {
    assert.doesNotMatch(s, FORBIDDEN, s);
    assert.doesNotMatch(s, /larsson/i, s);
    assert.doesNotMatch(s, /\p{Extended_Pictographic}/u, s);
    assert.doesNotMatch(s, /undefined|NaN|null/, s);
  }
});

test('each popover is 90 words or fewer', () => {
  const live = { logged: 14, scored: 13, mid: { uptrend: [6, 13], btc: [7, 13], alt: [6, 12] }, out: {} };
  const pops = [
    COPY.pop.fan({ state: 'on', side: 'either', since: 'May 2021', width: 15, today: '82%', paths: 12, runs: 8, tooFew: false, check: makeFan().check, live }),
    COPY.pop.fan({ state: 'off', side: 'holding', since: 'May 2021', width: 5, today: '82%', paths: 12, runs: 8, tooFew: false, check: makeFan().check, live: null }),
    COPY.pop.fan({ state: 'on', side: 'below', since: 'May 2021', width: 5, today: '82%', paths: 12, runs: 8, tooFew: false,
      check: { scored: 52, series: { uptrend: { pass: true }, btc: { pass: true }, alt: { pass: true } }, median_vs_all: 1.2 }, live }),
    COPY.pop.uptrend({ coins: 151, since: 'May 2021' }), COPY.pop.band(), COPY.pop.runs({ on: true, since: 'May 2021' }), COPY.pop.runs({ on: false, since: 'May 2021' }),
    COPY.pop.episodes({ alt: '−7.4%', btc: '+0.3%', from: 'May 2021', to: 'Mar 2026', end: '29 Mar 2026', better: 9, n: 18,
      verdict: { episodes: 9, alt: { direction: 'continuation', above_base: 7 } } }),
    COPY.pop.ft({ declared: '26 Sep 2026', share: 55, base: '−13.1%', bear: 5, n: 8 }), COPY.pop.past({ n: 8, base: '−13.1%' }), COPY.pop.fg({ since: 'Feb 2018' }),
  ];
  for (const p of pops) assert.ok(popWords(p.join(' ')) <= 90, `${popWords(p.join(' '))}: ${p.join(' ')}`);
  // The live line shows once 12 or more are scored, and the fan popover still fits.
  assert.match(pops[0].join(' '), /Since 28 Sep 2026: 13 new episodes, middle half held 50%\./);
  assert.doesNotMatch(pops[1].join(' '), /Since/);
});

test('fan popover: check wording follows the official result', () => {
  const ctx = { state: 'on', side: 'holding', since: 'May 2021', width: 5, today: '82%', paths: 12, runs: 8, tooFew: false, live: null };
  assert.match(COPY.pop.fan({ ...ctx, check: makeFan().check })[0], /the BTC and Uptrend bands held too few real moves, so their paths are drawn/);
  assert.match(COPY.pop.fan({ ...ctx, check: { scored: 52, series: { uptrend: { pass: true }, btc: { pass: true }, alt: { pass: true } }, median_vs_all: 1.13 } })[0],
    /median was further off than all past days/);
  assert.match(COPY.pop.fan({ ...ctx, check: { untested: true } })[0], /Too few past episodes to test the bands/);
  assert.match(COPY.pop.fan({ ...ctx, tooFew: true, runs: 5 })[0], /Only 5 runs: too few for a median or bands/);
  assert.match(COPY.pop.fan({ ...ctx, side: 'either', check: null })[0], /BTC either side of its weekly band/);
});

test('visible words stay within budget: 80 on the Uptrend tab, 20 on Fear & Greed', () => {
  const p = makePayload();
  for (const range of ['3m', '1y']) assert.ok(visibleWords('breadth', p, { range }) <= 80, String(visibleWords('breadth', p, { range })));
  assert.ok(visibleWords('breadth', makePayload({ cycle: { ...p.cycle, below_days: 2 } })) <= 80);
  assert.ok(visibleWords('fear', p) <= 20, String(visibleWords('fear', p)));
  assert.equal(countWords('82% Uptrend · +30d 7 of 12'), 3);
  const ctx = breadthContext(p);
  assert.equal(ctx.side, 'above');
  assert.equal(ctx.fanCtx.paths, 3);
});

test('formatting', () => {
  assert.deepEqual(logTicks(15000, 110000), [20000, 50000, 100000]);
  assert.ok(logTicks(60000, 95000).length >= 2);
  assert.equal(dayDate(20721), '25 Sep 2026');
  assert.equal(signedPct(-7.4), '−7.4%');
  assert.deepEqual(altTicks(38), [-25, 0, 25]);
  assert.deepEqual(altTicks(4), [-5, 0, 5]);
});
