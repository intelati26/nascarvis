// node tests/test_leaderssql.js
// Pins the SQL text leaderssql.js writes for a few settings (the behaviour against a database is in test_leaderssql.py) and the builder link.
const S = require('../leaderssql.js'), assert = require('assert');
const base = {stat: 'wins', scope: 'career', from: 1949, to: 2026, minStarts: 20, exactWins: null, top: 50, explain: false};

assert.strictEqual(S.leaders(base).sql, `-- Leaders: Wins, career, 1949-2026
SELECT
  r.driver AS "driver",
  MIN(r.season) AS "first_season",
  MAX(r.season) AS "last_season",
  SUM(r.finish = 1) AS "wins",
  COUNT(*) AS "starts",
  SUM(r.finish <= 5) AS "top5",
  SUM(r.finish <= 10) AS "top10",
  SUM(r.start = 1) AS "poles",
  SUM(r.led) AS "laps_led",
  ROUND(AVG(r.finish), 1) AS "avg_finish"
FROM results r
WHERE r.series = 'Cup'
  AND r.season >= 1949
  AND r.season <= 2026
GROUP BY r.driver
ORDER BY SUM(r.finish = 1) DESC, COUNT(*) DESC
LIMIT 50`, 'career wins: no HAVING, the minimum starts is for rates only');

assert.strictEqual(S.leaders({...base, stat: 'avgfin', scope: 'season', from: 2001, to: 2025, minStarts: 20, exactWins: 1, top: 25}).sql, `-- Leaders: Average finish, single season, 2001-2025
SELECT
  r.driver AS "driver",
  r.season AS "season",
  ROUND(AVG(r.finish), 2) AS "avg_finish",
  COUNT(*) AS "starts",
  SUM(r.finish = 1) AS "wins",
  SUM(r.finish <= 5) AS "top5",
  SUM(r.finish <= 10) AS "top10",
  SUM(r.start = 1) AS "poles",
  SUM(r.led) AS "laps_led"
FROM results r
WHERE r.series = 'Cup'
  AND r.season >= 2001
  AND r.season <= 2025
GROUP BY r.driver, r.season
HAVING COUNT(*) >= 20
  AND SUM(r.finish = 1) = 1
ORDER BY AVG(r.finish) ASC, COUNT(*) DESC
LIMIT 25`, 'single-season average finish: ascending, two HAVING conditions, the stat is not repeated');

const ex = S.leaders({...base, explain: true}).sql.split('\n');
assert.ok(ex.filter(l => l.startsWith('-- ')).length >= 6 && ex[1].startsWith('-- SELECT'), 'explain adds a comment before each clause');
assert.ok(!S.leaders({...base, explain: true}).sql.includes('HAVING'), 'no HAVING comment when there is no HAVING');

// the spec
const sp = S.leaders({...base, stat: 'winpct', exactWins: 2}).spec;
assert.deepStrictEqual(sp.params, {series: 'Cup', min_season: 1949, max_season: 2026, limit: 50, min_starts: 20, wins: 2});
assert.deepStrictEqual(sp.qualifier, {name: 'min_starts'});
assert.deepStrictEqual(sp.aggregate_filters, [{measure: 'wins', op: '=', param: 'wins'}]);
assert.deepStrictEqual(sp.sort, [{by: 'win_rate', dir: 'desc'}, {by: 'starts', dir: 'desc'}]);
assert.ok(sp.measures.includes('first_season') && sp.group_by.length === 1);
assert.deepStrictEqual(S.leaders({...base, stat: 'starts'}).spec.sort, [{by: 'starts', dir: 'desc'}]);
assert.strictEqual(S.leaders({...base, stat: 'poles'}).spec.qualifier, undefined);

// the builder link round-trips
const url = S.builderUrl(sp), enc = url.split('#spec=')[1];
assert.ok(/^[A-Za-z0-9_-]+$/.test(enc), 'base64url, safe in a URL hash');
assert.deepStrictEqual(JSON.parse(Buffer.from(enc.replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString('utf8')), sp);

assert.throws(() => S.leaders({...base, stat: 'nope'}), /unknown stat/);
console.log('all checks passed');
