// python tests/make_fixture.py && node tests/test_formats.js
// Checks formats.js against official final standings copied from the Wikipedia season articles
// (tests/official_standings_*.json, CC BY-SA).
//   2004-2013 Chase formats: the top 15 final totals and ranks must match (one name-spelling quirk allowed).
//   2014-2025 elimination formats: the playoff field, champion, final-four order and totals must match;
//   eliminated drivers' totals/ranks are held to a tolerance (see the README for the known residuals).
const F = require('../formats.js'), fs = require('fs');
const data = JSON.parse(fs.readFileSync(__dirname + '/results_2004_2025.json'));
F.setAdjustments(JSON.parse(fs.readFileSync(__dirname + '/../adjustments.json')));
const norm = s => s.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/\./g, '').replace(/\s+/g, ' ').trim().toLowerCase();
let fails = 0; const fail = m => { fails++; console.log('  FAIL', m); };

// ---- 2004-2013 (Chase)
const off1 = JSON.parse(fs.readFileSync(__dirname + '/official_standings_2004_2013.json'));
for (const y of Object.keys(off1)) {
  const st = F.compute(+y, data[y], 'auto'), k = st.nums.length - 1;
  const map = new Map(st.drivers.map(d => [norm(d), d]));
  let bad = 0;
  for (const [pos, name, pts] of off1[y].slice(0, 15)) {
    const d = map.get(norm(name)); if (!d) continue;                 // spelling quirk (e.g. "A. J.")
    if (st.pts.get(d)[k] !== pts || st.rank.get(d)[k] !== pos) { bad++; fail(`${y} ${name}: official ${pos}/${pts}, got ${st.rank.get(d)[k]}/${st.pts.get(d)[k]}`); }
  }
  console.log(y, st.format, bad ? 'MISMATCH' : 'ok');
}

// ---- 2014-2025 (elimination)
const off2 = JSON.parse(fs.readFileSync(__dirname + '/official_standings_2014_2025.json'));
let n = 0, within5 = 0, rankOk = 0;
for (const y of Object.keys(off2)) {
  const st = F.compute(+y, data[y], 'auto'), k = st.nums.length - 1;
  const map = new Map(st.drivers.map(d => [norm(d), d]));
  const rows = off2[y].filter(r => r.pos <= 16 && r.pts > 500).map(r => ({ ...r, d: map.get(norm(r.name)) })).filter(r => r.d);
  const fieldNames = off2[y].filter(r => r.pos <= 16).map(r => map.get(norm(r.name))).filter(Boolean);
  let line = [];
  if (+y >= 2017) {
    const miss = fieldNames.filter(d => !st.field.has(d)), extra = [...st.field].filter(d => !fieldNames.includes(d) && off2[y].length > 16);
    if (miss.length || extra.length) fail(`${y} field differs: missing ${miss}, extra ${extra}`);
  }
  rows.slice(0, 4).forEach(r => { if (st.rank.get(r.d)[k] !== r.pos || st.pts.get(r.d)[k] !== r.pts) fail(`${y} finalist ${r.name}: official ${r.pos}/${r.pts}, got ${st.rank.get(r.d)[k]}/${st.pts.get(r.d)[k]}`); });
  rows.slice(4).forEach(r => { n++; if (Math.abs(st.pts.get(r.d)[k] - r.pts) <= 5) within5++; if (st.rank.get(r.d)[k] === r.pos) rankOk++; });
  console.log(y, st.format, 'champion', rows[0].name, '->', st.drivers.find(d => st.rank.get(d)[k] === 1));
}
const pct = (a, b) => Math.round(100 * a / b);
console.log(`eliminated drivers: totals within 5 pts ${within5}/${n} (${pct(within5, n)}%), exact rank ${rankOk}/${n} (${pct(rankOk, n)}%)`);
if (pct(within5, n) < 85) fail('eliminated totals within 5 below 85%');
if (pct(rankOk, n) < 85) fail('eliminated rank exact below 85%');
console.log(fails ? `${fails} FAILURES` : 'all checks passed');
process.exit(fails ? 1 : 0);
