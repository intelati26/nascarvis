// Points formats ("eras") for NASCAR Cup seasons. Pure functions, no DOM: inlined into the
// dashboard by build_dashboard.py and unit-tested under node (test_formats.js).
//
// A format decides who is in the playoff field after the regular season, how the field's points are
// reset, and how win bonuses work. Any format can be applied to any season ("what ifs").
// Elimination formats (2014-2025) are modelled in the `elim` branch of compute().
const NASCARFormats = (function () {
  const BONUS_2026 = [100, 75, 65, 60, 55, 50, 45, 40, 35, 30, 25, 20, 15, 10, 5, 0];

  // field: how drivers qualify.   seed(rank, wins, wildcard): the reset points.
  const FORMATS = {
    full:    { label: 'Full season (no reset)', short: 'Full season' },
    chase04: { label: '2004–06 Chase: top 10 + within 400 pts, reset 5050 down by 5', short: '2004–06 Chase',
               field: { top: 10, within: 400 }, seed: r => 5050 - 5 * (r - 1) },
    chase07: { label: '2007–10 Chase: top 12, reset 5000 + 10 per win', short: '2007–10 Chase',
               field: { top: 12 }, seed: (r, w) => 5000 + 10 * w },
    chase11: { label: '2011–13 Chase: top 10 + 2 wild cards, reset 2000 + 3 per win', short: '2011–13 Chase',
               field: { top: 10, wild: 2 }, seed: (r, w, wc) => 2000 + (wc ? 0 : 3 * w) },
    elim14:  { label: '2014–16 Elimination: 16 drivers, win-and-in, rounds of 16/12/8/4, resets 2000+3/win, 3000, 4000, 5000', short: '2014–16 Elimination',
               elim: { winnersBy: 'wins', pp: false } },
    elim17:  { label: '2017–25 Elimination: 16 drivers, playoff points + stage points, rounds of 16/12/8/4, resets 2000+PP, 3000+PP, 4000+PP, 5000', short: '2017–25 Elimination',
               elim: { winnersBy: 'points', pp: true, ppImmediate: true } },
    chase26: { label: '2026 Chase: top 16, reset 2000 + 100/75/65/60…0 by rank', short: '2026 Chase',
               field: { top: 16 }, seed: r => 2000 + (BONUS_2026[r - 1] || 0) },
  };

  // The format actually run in a season. 2014-2025 used elimination rounds (not modelled here).
  function eraFormat(season) {
    if (season >= 2026) return 'chase26';
    if (season >= 2017) return 'elim17';
    if (season >= 2014) return 'elim14';
    if (season >= 2011) return 'chase11';
    if (season >= 2007) return 'chase07';
    if (season >= 2004) return 'chase04';
    return 'full';
  }
  // Historic one-offs, applied only when the season's own format is in use.
  // 2013: Martin Truex Jr. was removed from the Chase after Richmond (race-manipulation penalties); Ryan Newman
// took his place and Jeff Gordon was added as a 13th driver.
const SPECIAL = {
  2013: { extra: ['Jeff Gordon', 'Ryan Newman'], exclude: ['Martin Truex Jr.'] },
  // Elimination era: wins that did not qualify the driver (encumbered / post-race inspection failures), or a driver
  // who withdrew from the playoffs. Sources: the season articles' notes; see README.
  2017: { noWin: ['Joey Logano'] },          // Richmond win was "encumbered": not playoff-eligible
  2022: { exclude: ['Kurt Busch'] },         // withdrew from the playoffs (concussion)
  2024: { noWin: ['Austin Dillon'] },        // Richmond win was not playoff-eligible
};

  // Known points adjustments (penalties) that the results data does not include:
  // { season: [ { race, driver, pts, note } ] }  (applied from `race` onward). Filled in by the build.
  let ADJUSTMENTS = {};
  // accepts the adjustments.json list: [{season, race, driver, pts, note}]
  function setAdjustments(list) {
    ADJUSTMENTS = {};
    (list || []).forEach(a => { (ADJUSTMENTS[a.season] = ADJUSTMENTS[a.season] || []).push(a); });
  }

  // races: [{num, rows:[{driver, pts, finish}]}] in race order.
  // fmt: key of FORMATS (or 'auto'); after: races before the playoff (default 26); adj: apply ADJUSTMENTS.
  function compute(season, races, fmt, opts) {
    opts = opts || {};
    const after = opts.after || 26, useAdj = opts.adj !== false;
    const era = eraFormat(season);
    const key = !fmt || fmt === 'auto' ? era : fmt;
    const F = FORMATS[key];
    const adj = useAdj ? (ADJUSTMENTS[season] || []) : [];

    const names = new Set(); races.forEach(r => r.rows.forEach(x => names.add(x.driver)));
    const ds = [...names], K = races.length;
    const reg = new Map(ds.map(d => [d, new Array(K).fill(0)]));      // cumulative raw points incl. penalties
    const wins = new Map(ds.map(d => [d, new Array(K).fill(0)]));
    const fins = new Map(ds.map(d => [d, new Array(K).fill(0)]));     // cumulative finish sum
    const cnt = new Map(ds.map(d => [d, new Array(K).fill(0)]));      // cumulative starts
    const started = new Map(ds.map(d => [d, new Array(K).fill(false)]));
    const finList = new Map(ds.map(d => [d, []]));     // finish per race (null if absent)
    const swList = new Map(ds.map(d => [d, []]));      // stage wins per race
    races.forEach((r, k) => {
      for (const d of ds) {
        const p = k ? { reg: reg.get(d)[k - 1], w: wins.get(d)[k - 1], f: fins.get(d)[k - 1], c: cnt.get(d)[k - 1], s: started.get(d)[k - 1] }
                    : { reg: 0, w: 0, f: 0, c: 0, s: false };
        const row = r.rows.find(x => x.driver === d);
        let pts = p.reg + (row ? (row.pts || 0) : 0);
        for (const a of adj) if (a.driver === d && a.race === r.num) pts += a.pts;
        reg.get(d)[k] = pts;
        wins.get(d)[k] = p.w + (row && row.finish === 1 ? 1 : 0);
        fins.get(d)[k] = p.f + (row ? row.finish : 0);
        cnt.get(d)[k] = p.c + (row ? 1 : 0);
        started.get(d)[k] = p.s || !!row;
        finList.get(d).push(row ? row.finish : null);
        swList.get(d).push(row ? (row.sw || 0) : 0);
      }
    });

    // --- playoff field, chosen on the standings after race `after`
    let field = null, seeds = null, resetIdx = null, wild = new Set();
    if (F.field && K > after) {
      const kk = after - 1;
      const sp = key === era ? SPECIAL[season] : null;
      const order = ds.filter(d => started.get(d)[kk] && !(sp && sp.exclude && sp.exclude.includes(d))).sort((a, b) =>
        reg.get(b)[kk] - reg.get(a)[kk] || wins.get(b)[kk] - wins.get(a)[kk] ||
        fins.get(a)[kk] / (cnt.get(a)[kk] || 1) - fins.get(b)[kk] / (cnt.get(b)[kk] || 1));
      const f = order.slice(0, F.field.top);
      if (F.field.within) {
        const lead = reg.get(order[0])[kk];
        order.slice(F.field.top).forEach(d => { if (reg.get(d)[kk] >= lead - F.field.within) f.push(d); });
      }
      if (F.field.wild) {
        order.slice(F.field.top, 20).map((d, i) => ({ d, i, w: wins.get(d)[kk] }))
          .sort((a, b) => b.w - a.w || a.i - b.i).slice(0, F.field.wild).forEach(x => { f.push(x.d); wild.add(x.d); });
      }
      if (sp) sp.extra.forEach(d => { if (!f.includes(d) && started.get(d)[kk]) { f.push(d); wild.add(d); } });
      field = new Set(f);
      seeds = new Map();
      // seed rank = position in regular-season order (wild cards seeded after the automatic qualifiers)
      const seedOrder = f.filter(d => !wild.has(d)).concat(f.filter(d => wild.has(d)));
      seedOrder.forEach((d, i) => seeds.set(d, F.seed(i + 1, wins.get(d)[kk], wild.has(d))));
      resetIdx = after;
    }

    // Tiebreak at race index k: most wins, then most 2nd places, 3rd places, ... (NASCAR's rule).
    const countsUpTo = (d, k, pos) => { let n = 0; const f = finList.get(d); for (let i = 0; i <= k; i++) if (f[i] === pos) n++; return n; };
    const tie = (a, b, k) => {
      for (let pos = 1; pos <= 43; pos++) { const x = countsUpTo(a, k, pos), y = countsUpTo(b, k, pos); if (x !== y) return y - x; }
      return 0;
    };

    // --- elimination formats (2014-2025): 16 drivers, rounds of 16/12/8/4, finale decides the title
    if (F.elim && K > after) return elimStandings();

    function elimStandings() {
      const E = F.elim, kk = after - 1;
      const inc = (d, k) => reg.get(d)[k] - (k ? reg.get(d)[k - 1] : 0);
      const earned = (d, k) => { const f = finList.get(d)[k]; return f == null ? 0 : (f === 1 ? 5 : 0) + (swList.get(d)[k] || 0); };
      // finishing points for the finale: 43-point scale 2014-15, 40-point scale in 2016, stage-era scale from 2017
      const finPts = f => E.pp ? (f === 1 ? 40 : Math.max(1, 37 - f)) : Math.max(1, (season >= 2016 ? 41 : 44) - f);

      // qualification: race winners first, then by points. A win only counts for a driver in the top 30 in points or one who attempted every race.
      const sp = key === era ? SPECIAL[season] : null;
      const order = ds.filter(d => started.get(d)[kk] && !(sp && sp.exclude && sp.exclude.includes(d)))
        .sort((a, b) => reg.get(b)[kk] - reg.get(a)[kk] || tie(a, b, kk));
      let win = order.filter((d, i) => wins.get(d)[kk] >= 1 && (i < 30 || cnt.get(d)[kk] >= after) && !(sp && sp.noWin && sp.noWin.includes(d)));
      if (win.length > 16) {
        if (E.winnersBy === 'wins') win = win.slice().sort((a, b) => wins.get(b)[kk] - wins.get(a)[kk] || order.indexOf(a) - order.indexOf(b));
        win = win.slice(0, 16);
      }
      const f = win.slice();
      order.forEach(d => { if (f.length < 16 && !f.includes(d)) f.push(d); });
      const field = new Set(f);

      // playoff points (2017+): 5 per win, 1 per stage win, plus 15/10/8/7/6/5/4/3/2/1 for the regular-season top 10
      const REG_BONUS = [15, 10, 8, 7, 6, 5, 4, 3, 2, 1];
      const PP = new Map(), seeds = new Map();
      ds.forEach(d => {
        let p = 0; for (let i = 0; i <= kk; i++) p += earned(d, i);
        PP.set(d, p + (E.pp ? (REG_BONUS[order.indexOf(d)] || 0) * (order.indexOf(d) < 10 ? 1 : 0) : 0));
      });
      f.forEach(d => seeds.set(d, 2000 + (E.pp ? PP.get(d) : 3 * wins.get(d)[kk])));

      const BASE = [2000, 3000, 4000, 5000], SIZE = [16, 12, 8, 4];
      const ppNow = new Map(PP);
      const roundStart = r => after + 3 * r;
      const out = { drivers: ds, nums: races.map(r => r.num), pts: new Map(), rank: new Map(), behind: new Map(),
                    started, field, resetIdx: after, resetIdxs: [], format: key, auto: key === era, wild: new Set(),
                    wins, adj, seeds, regPts: reg, rounds: [], elimRound: new Map(), playoffPts: PP, ppEnd: ppNow };
      ds.forEach(d => { out.pts.set(d, new Array(K).fill(null)); out.rank.set(d, new Array(K).fill(null)); out.behind.set(d, new Array(K).fill(null)); });

      // before the playoffs: plain cumulative points
      const place = (k, groups) => {      // groups: [[drivers sorted], ...]; ranks run on through the groups
        let base = 0;
        for (const g of groups) {
          const top = g.length ? out.pts.get(g[0])[k] : 0;
          g.forEach((d, j) => {
            const prev = g[j - 1];
            const same = j > 0 && out.pts.get(prev)[k] === out.pts.get(d)[k] && tie(prev, d, k) === 0 && g.finalOrder !== true;
            out.rank.get(d)[k] = same ? out.rank.get(prev)[k] : base + j + 1;
            out.behind.get(d)[k] = out.pts.get(d)[k] - top;
          });
          base += g.length;
        }
      };
      for (let k = 0; k < Math.min(after, K); k++) {
        ds.forEach(d => { out.pts.get(d)[k] = reg.get(d)[k]; });
        const act = ds.filter(d => started.get(d)[k]).sort((a, b) => out.pts.get(b)[k] - out.pts.get(a)[k] || tie(a, b, k));
        place(k, [act]);
      }

      let cur = new Set(f), roundPts = new Map(), cont = new Map();
      ppNow.forEach((v, d) => ppNow.set(d, PP.get(d)));
      const tiers = [];                      // drivers eliminated per round, earliest first
      let lastFinale = null;
      for (let k = after; k < K; k++) {
        const r = k >= after + 9 ? 3 : Math.floor((k - after) / 3);
        if (k === roundStart(r) || (r === 3 && k === after + 9)) {
          out.resetIdxs.push(k);
          cur.forEach(d => roundPts.set(d, r === 0 ? seeds.get(d) : BASE[r] + (E.pp && r < 3 ? ppNow.get(d) : 0)));
          if (r === 0) cur.forEach(d => cont.set(d, seeds.get(d)));
        }
        for (const d of cur) {
          roundPts.set(d, roundPts.get(d) + inc(d, k) + (E.ppImmediate && E.pp ? earned(d, k) : 0));
          if (E.pp && r < 3) ppNow.set(d, ppNow.get(d) + earned(d, k));
        }
        // eliminated drivers keep scoring points through the finale
        for (const d of f) if (!E.freeze || cur.has(d)) cont.set(d, cont.get(d) + inc(d, k) + (E.ppImmediate && E.pp ? earned(d, k) : 0));
        // eliminate at the end of a round
        if (r < 3 && k === roundStart(r) + 2) {
          const slots = SIZE[r + 1], inRound = [...cur];
          const rw = inRound.filter(d => { for (let i = roundStart(r); i <= k; i++) if (finList.get(d)[i] === 1) return true; return false; });
          const byPts = (a, b) => roundPts.get(b) - roundPts.get(a) || tie(a, b, k);
          const adv = rw.sort(byPts).slice(0, slots);
          inRound.filter(d => !adv.includes(d)).sort(byPts).forEach(d => { if (adv.length < slots) adv.push(d); });
          const gone = inRound.filter(d => !adv.includes(d));
          tiers.push(gone); gone.forEach(d => out.elimRound.set(d, r + 1));
          out.rounds.push({ start: roundStart(r), advanced: adv.slice(), eliminated: gone.slice() });
          out.advancedAt = out.advancedAt || [];
          // playoff points earned in the last round are not carried into the finale reset
          if (E.pp && r === 2) adv.forEach(d => { for (let i = roundStart(r); i <= k; i++) ppNow.set(d, ppNow.get(d) - earned(d, i)); });
          cur = new Set(adv);
        }
        // display points and rank
        const eliminatedAll = [].concat(...tiers);      // official standings rank every eliminated driver together, by points
        ds.forEach(d => {
          if (cur.has(d) && !(r === 3 && k === K - 1 && false)) out.pts.get(d)[k] = roundPts.get(d);
          else if (field.has(d)) out.pts.get(d)[k] = cont.get(d);
          else out.pts.get(d)[k] = reg.get(d)[k];
        });
        const nonField = ds.filter(d => started.get(d)[k] && !field.has(d));
        const sorter = (a, b) => out.pts.get(b)[k] - out.pts.get(a)[k] || tie(a, b, k);
        let groups;
        const finale = r === 3 && k === after + 9;
        if (finale) {
          // the title goes to the best finisher among the final four; their points are 5000 + finishing points
          const four = [...cur].sort((a, b) => (finList.get(a)[k] ?? 99) - (finList.get(b)[k] ?? 99));
          four.forEach(d => { const fp = finList.get(d)[k]; out.pts.get(d)[k] = 5000 + (fp == null ? 0 : finPts(fp)); });
          four.finalOrder = true;
          groups = [four];
        } else groups = [[...cur].sort(sorter)];
        groups.push(eliminatedAll.slice().sort(sorter));
        groups.push(nonField.sort(sorter));
        place(k, groups);
      }
      return out;
    }

    // --- points, rank, gap
    const out = { drivers: ds, nums: races.map(r => r.num), pts: new Map(), rank: new Map(), behind: new Map(),
                  started, field, resetIdx, format: key, auto: key === era, wild,
                  wins, adj, seeds, regPts: reg };
    ds.forEach(d => { out.pts.set(d, []); out.rank.set(d, []); out.behind.set(d, []); });
    for (let k = 0; k < K; k++) {
      for (const d of ds) {
        const raw = reg.get(d)[k];
        out.pts.get(d)[k] = field && k >= resetIdx && field.has(d) ? seeds.get(d) + raw - reg.get(d)[resetIdx - 1] : raw;
      }
      const active = ds.filter(d => started.get(d)[k]);
      const grouped = field && k >= resetIdx;
      const groups = grouped ? [active.filter(d => field.has(d)), active.filter(d => !field.has(d))] : [active];
      let base = 0;
      for (const g of groups) {
        g.sort((a, b) => out.pts.get(b)[k] - out.pts.get(a)[k] || tie(a, b, k));
        const top = g.length ? out.pts.get(g[0])[k] : 0;
        g.forEach((d, j) => {
          const same = j > 0 && out.pts.get(g[j - 1])[k] === out.pts.get(d)[k] && tie(g[j - 1], d, k) === 0;
          out.rank.get(d)[k] = same ? out.rank.get(g[j - 1])[k] : base + j + 1;
          out.behind.get(d)[k] = out.pts.get(d)[k] - top;
        });
        base += g.length;
      }
      for (const d of ds) if (out.rank.get(d)[k] === undefined) { out.rank.get(d)[k] = null; out.behind.get(d)[k] = null; }
    }
    return out;
  }

  return { FORMATS, eraFormat, compute, setAdjustments, SPECIAL };
})();
if (typeof module !== 'undefined') module.exports = NASCARFormats;
