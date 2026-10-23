// node tests/test_wikitext.js
// Checks wikitext.js against the layout of WikiProject NASCAR's results tables (see the header of wikitext.js for the pages it follows).
const W = require('../wikitext.js'), assert = require('assert');
let fails = 0; const ok = (c, m) => { if (!c) { fails++; console.log('  FAIL', m); } };

const slots = n => Array.from({length: n}, (_, i) => ({num: i + 1, track: ['Daytona International Speedway', 'Richmond Raceway', 'Rockingham Speedway', 'Atlanta Motor Speedway', 'Bristol Motor Speedway', 'Nowhere Special Raceway'][i % 6], name: `Race ${i + 1}`}));
const e = (finish, extra = {}) => ({finish, start: 10, dnf: false, team: 'A Racing', car: 1, make: 'Ford', ...extra});

// ---- a season with two rides: races 1-2 for A Racing, 5-6 for B Motorsports
const s81 = {season: 1981, slots: slots(6), rank: 21, pts: 297.0,
  entries: {1: e(1), 2: e(2), 5: e(11, {team: 'B Motorsports', car: 13, make: 'Chevrolet'}), 6: e(40, {dnf: true, team: 'B Motorsports', car: 13, make: 'Chevrolet'})}};
const t = W.seriesTable(W.seriesOf(1981), [s81], {});
const lines = t.split('\n');
ok(lines[0] === '====Winston Cup Series====', 'series heading');
ok(lines[1] === '{| class="wikitable" style="text-align:center; font-size:75%"', 'table class');
ok(lines.includes('!colspan=13| [[NASCAR]] [[Winston Cup Series]] results'), 'title row spans width + 7 columns (4 + 6 races + 3)');
ok(lines.includes('! {{Tooltip|NWCC|NASCAR Winston Cup classification}}'), 'NWCC header');
ok(lines.includes('! rowspan=2| [[1981 NASCAR Winston Cup Series|1981]]'), 'year cell spans both rides and links the season article');
ok(lines.includes('! rowspan=2| 21st') && lines.includes('! rowspan=2| 297'), 'rank and points span both rides');
ok(lines.includes('| style="background:#FFFFBF;"| DAY<br>{{small|1}}'), 'win is gold');
ok(lines.includes('| style="background:#DFDFDF;"| RCH<br>{{small|2}}'), '2nd is silver');
ok(lines.includes('| style="background:#DFFFDF;"| BRI<br>{{small|11}}'), '11th is green');
ok(lines.includes('| style="background:#EFCFFF;"| ??N<br>{{small|40}}'.replace('??N', W.code('Nowhere Special Raceway'))), 'DNF is purple, whatever the finish');
// row 1: two coloured cells, two plain cells, then the other ride's races merged into one blank cell
const r1 = lines.slice(lines.indexOf('! A Racing'));
assert.deepStrictEqual(r1.slice(3, 8), ['| style="background:#FFFFBF;"| DAY<br>{{small|1}}', '| style="background:#DFDFDF;"| RCH<br>{{small|2}}', '| CAR', '| ATL', '| colspan=2|'],
  'first ride: races 1-2 coloured, 3-4 plain, 5-6 merged blank');
const r2 = lines.slice(lines.indexOf('! B Motorsports'));
ok(r2[3] === '| colspan=2|' && r2[4] === '| CAR' && r2[5] === '| ATL', 'second ride: races 1-2 blank (merged), 3-4 plain');
ok(lines.includes('! [[Chevrolet]]') && lines.includes('! [[Ford Motor Company|Ford]]'), 'known makes are linked');

// ---- every row covers exactly the table's width
const cols = block => { let n = 0; for (const l of block) { const m = /^\| (?:style="[^"]*"\| )?.*$/.test(l); if (/^\|( colspan=(\d+)\|)?$/.test(l)) n += +(/colspan=(\d+)/.exec(l) || [0, 1])[1]; else if (m) n++; } return n; };
const rowsOf = txt => txt.split('\n|-').slice(3).map(b => b.split('\n').filter(l => l.startsWith('|') && !l.startsWith('|}')));
for (const r of rowsOf(t)) ok(cols(r) === 6, `each row has 6 race columns, got ${cols(r)}`);

// ---- shorter seasons are padded to the widest
const s70 = {season: 1969, slots: slots(4), rank: 3, pts: 100, entries: {1: e(5)}};
const g = W.grid([s70, s81], {});
ok(g.indexOf('====Grand National Series====') < g.indexOf('====Winston Cup Series===='), 'eras split into one table each, oldest first');
ok(g.includes('[[1969 NASCAR Grand National Series|1969]]') && g.includes('{{Tooltip|NGNC|'), 'Grand National article and classification');
ok(g.includes('==Motorsports career results==') && g.includes('===NASCAR===') && g.includes('[[Template:NASCAR driver results legend|key]]'), 'section titles and key line');
ok(g.includes('<!-- Track codes guessed from initials'), 'unmapped track is flagged');

// ---- options
ok(W.seriesTable(W.seriesOf(1981), [{...s81, entries: {1: e(1, {start: 1})}}], {pole: true}).includes("'''DAY'''<br>{{small|1}}"), 'pole option bolds the code');
ok(W.seriesTable(W.seriesOf(1981), [s81], {link: true}).includes('| style="background:#FFFFBF;"| [[Race 1|DAY]]<br>{{small|1}}'), 'link option links the race');
ok(!W.seriesTable(W.seriesOf(1981), [s81], {}).includes('[['+'Race 1'), 'races are not linked by default');
ok(!W.seriesTable(W.seriesOf(1981), [s81], {ref: false}).includes('! Ref'), 'ref column can be left out');
ok(W.seriesTable(W.seriesOf(1981), [{...s81, entries: {1: e(30, {dsq: true})}}], {}).includes('style="background:#000000; color:white"| <span style="color:white;">DAY</span><br>{{small|30}}'), 'DSQ is black with white text');
ok(W.seriesTable(W.seriesOf(1981), [{...s81, entries: {1: e(40, {dns: true})}}], {}).includes('| DAY<br>{{small|DNS}}'), 'DNS has no colour');

// ---- eras and ordinals
ok(W.seriesOf(1949).heading === 'Strictly Stock Series' && W.seriesOf(1970).heading === 'Grand National Series' && W.seriesOf(2003).heading === 'Winston Cup Series' &&
   W.seriesOf(2004).heading === 'Nextel Cup Series' && W.seriesOf(2016).heading === 'Sprint Cup Series' && W.seriesOf(2025).heading === 'Cup Series', 'series by year');
ok(W.SERIES[5].article(2018) === 'Monster Energy NASCAR Cup Series' && W.SERIES[5].article(2022) === 'NASCAR Cup Series', 'Cup Series article names');
ok([1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 61, 101, 111].map(W.ordinal).join() === '1st,2nd,3rd,4th,11th,12th,13th,21st,22nd,23rd,61st,101st,111th', 'ordinals');

// ---- the project's career-results table
const s = W.summary([{season: 1986, rank: 21, pts: 2705, starts: 23, wins: 0, t5: 1, t10: 4, avgstart: 22.1, avgfin: 15.7}, {season: 1985, rank: 40, pts: 509, starts: 5, wins: 0, t5: 0, t10: 0, avgstart: 25.7, avgfin: 20.3}]).split('\n');
ok(s[1] === '{| class="wikitable sortable" border="1" style="font-size:80%; text-align:left;"', 'summary uses the quickbio table class');
ok(s[3] === '! Year  || Rank || Points || Starts || Wins || Top 5 || Top 10 || Avg. Start || Avg. Finish', 'summary header matches quickbio minus winnings');
ok(s[5] === '|1985 ||40 ||509 ||5 ||0 ||0 ||0 ||25.7 ||20.3' && s[7] === '|1986 ||21 ||2705 ||23 ||0 ||1 ||4 ||22.1 ||15.7', 'summary rows sorted by year');

console.log(fails ? `${fails} FAILED` : 'all checks passed');
process.exit(fails ? 1 : 0);
