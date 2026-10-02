// python tests/make_fixture.py && node tests/test_formats.js
// Compares each season's computed final standings (top 15) with the official ones in
// official_standings_2004_2013.json (final points from the Wikipedia season articles).
const F = require('../formats.js');
const fs = require('fs');
const data = JSON.parse(fs.readFileSync(__dirname + '/results_2004_2013.json')), off = JSON.parse(fs.readFileSync(__dirname + '/official_standings_2004_2013.json'));
F.setAdjustments(JSON.parse(fs.readFileSync(__dirname + '/../adjustments.json')));
// Known and explained: 2011 'A. J.' vs 'A.J.' spelling of one name in the official list.
const KNOWN = 1;
let bad = 0;
for (const y of Object.keys(off)) {
  const st = F.compute(+y, data[y], 'auto');
  const k = st.nums.length - 1;
  const mine = st.drivers.filter(d => st.started.get(d)[k]).sort((a, b) => st.rank.get(a)[k] - st.rank.get(b)[k]);
  const lines = [];
  for (const [pos, name, pts] of off[y].slice(0, 15)) {
    const m = st.pts.get(name);
    const got = m ? m[k] : null, rk = m ? st.rank.get(name)[k] : null;
    if (got !== pts || rk !== pos) { lines.push(`   ${pos}. ${name}: official ${pts} got ${got} (rank ${rk}) diff ${got == null ? '?' : got - pts}`); bad++; }
  }
  console.log(y, st.format, 'field', [...(st.field || [])].length, lines.length ? 'MISMATCH' : 'ok');
  lines.forEach(l => console.log(l));
}
console.log('total mismatches', bad);
process.exit(bad > KNOWN ? 1 : 0);
