// "Show as SQL" for the Leaders tab: the SQL that gives the same table as the current leaderboard settings, written to be read and
// changed, plus the matching spec for the query builder (query/query.html). Pure functions, no DOM: inlined into the dashboard by
// build_dashboard.py and unit-tested under node (tests/test_leaderssql.js) and against a real database (tests/test_leaderssql.py).
//
// The SQL runs on the `results` table built by query/build_db.py (one row per driver per race). Column and measure definitions are the
// ones in query/catalog_nascar.json, so a leaderboard and the builder never disagree about what a win or a DNF is.
const NASCARSql = (function () {
  // One entry per option of the Stat menu. `measure` is the catalog measure of the same meaning (the builder spec uses it); `order` is the unrounded
  // expression to sort by, so the order is the dashboard's even where the shown value is rounded; `rate` stats take the minimum-starts filter.
  const STATS = {
    wins:   {label: 'Wins',           alias: 'wins',       expr: 'SUM(r.finish = 1)',         measure: 'wins'},
    top5:   {label: 'Top 5s',         alias: 'top5',       expr: 'SUM(r.finish <= 5)',        measure: 'top5'},
    top10:  {label: 'Top 10s',        alias: 'top10',      expr: 'SUM(r.finish <= 10)',       measure: 'top10'},
    starts: {label: 'Starts',         alias: 'starts',     expr: 'COUNT(*)',                  measure: 'starts'},
    poles:  {label: 'Poles (start P1)', alias: 'poles',    expr: 'SUM(r.start = 1)',          measure: 'poles'},
    led:    {label: 'Laps led',       alias: 'laps_led',   expr: 'SUM(r.led)',                measure: 'laps_led'},
    dnf:    {label: 'DNFs',           alias: 'dnfs',       expr: "SUM(r.status <> 'running')", measure: 'dnfs'},
    winpct: {label: 'Win %',          alias: 'win_pct',    expr: 'ROUND(100.0 * SUM(r.finish = 1) / COUNT(*), 1)',   order: '100.0 * SUM(r.finish = 1) / COUNT(*)',   measure: 'win_rate',   rate: true},
    t5pct:  {label: 'Top-5 %',        alias: 'top5_pct',   expr: 'ROUND(100.0 * SUM(r.finish <= 5) / COUNT(*), 1)',   order: '100.0 * SUM(r.finish <= 5) / COUNT(*)',  measure: 'top5_rate',  rate: true},
    t10pct: {label: 'Top-10 %',       alias: 'top10_pct',  expr: 'ROUND(100.0 * SUM(r.finish <= 10) / COUNT(*), 1)',  order: '100.0 * SUM(r.finish <= 10) / COUNT(*)', measure: 'top10_rate', rate: true},
    avgfin: {label: 'Average finish', alias: 'avg_finish', expr: 'ROUND(AVG(r.finish), 2)',   order: 'AVG(r.finish)',                                          measure: 'avg_finish', rate: true, low: true},
  };
  // The other columns of the Leaders table, in its order.
  const EXTRA = [
    {alias: 'starts',    expr: 'COUNT(*)',                 measure: 'starts'},
    {alias: 'wins',      expr: 'SUM(r.finish = 1)',        measure: 'wins'},
    {alias: 'top5',      expr: 'SUM(r.finish <= 5)',       measure: 'top5'},
    {alias: 'top10',     expr: 'SUM(r.finish <= 10)',      measure: 'top10'},
    {alias: 'poles',     expr: 'SUM(r.start = 1)',         measure: 'poles'},
    {alias: 'laps_led',  expr: 'SUM(r.led)',               measure: 'laps_led'},
    {alias: 'avg_finish', expr: 'ROUND(AVG(r.finish), 1)', measure: 'avg_finish'},
  ];

  const int = (v, d) => Number.isFinite(+v) && v !== '' && v !== null ? Math.trunc(+v) : d;

  // o: {stat, scope: 'career' | 'season', from, to, minStarts, exactWins (number or null), top, explain (bool), trackType (a key from track_types.py, or empty for all)}
  function leaders(o) {
    const S = STATS[o.stat]; if (!S) throw new Error(`unknown stat ${o.stat}`);
    const season = o.scope === 'season', from = int(o.from, 1949), to = int(o.to, 9999), top = Math.max(1, int(o.top, 50));
    const minStarts = S.rate ? Math.max(0, int(o.minStarts, 0)) : 0, exact = o.exactWins == null || o.exactWins === '' ? null : int(o.exactWins, null);
    const order = S.order || S.expr, dir = S.low ? 'ASC' : 'DESC';
    const tt = o.trackType || ''; if (tt && !/^[a-z_]+$/.test(tt)) throw new Error(`bad track type ${tt}`);
    const note = (text) => o.explain ? [`-- ${text}`] : [];

    const sel = ['r.driver AS "driver"'];
    sel.push(...(season ? ['r.season AS "season"'] : ['MIN(r.season) AS "first_season"', 'MAX(r.season) AS "last_season"']));
    sel.push(`${S.expr} AS "${S.alias}"`);
    for (const x of EXTRA) if (x.alias !== S.alias) sel.push(`${x.expr} AS "${x.alias}"`);

    const having = [];
    if (minStarts > 0) having.push(`COUNT(*) >= ${minStarts}`);
    if (exact !== null) having.push(`SUM(r.finish = 1) = ${exact}`);

    const L = [`-- Leaders: ${S.label}, ${season ? 'single season' : 'career'}, ${from}-${to}`];
    L.push(...note('SELECT lists the columns. Each SUM or COUNT adds up the races in the group; r.finish = 1 is true (1) for a win and false (0) otherwise.'));
    L.push('SELECT', sel.map(s => '  ' + s).join(',\n'));
    L.push(...note('FROM names the table: results has one row per driver per race. "r" is a short name for it.'));
    L.push('FROM results r');
    L.push(...note('WHERE keeps only the races inside the season range' + (tt ? ' and of this kind of track (r.track_type is decided per race: superspeedway, long, intermediate, road or short)' : '') + '. It runs before grouping.'));
    L.push(`WHERE r.series = 'Cup'`, `  AND r.season >= ${from}`, `  AND r.season <= ${to}`);
    if (tt) L.push(`  AND r.track_type = '${tt}'`);
    L.push(...note(season ? 'GROUP BY collapses the races into one row per driver and season.' : 'GROUP BY collapses all of a driver\'s races into one row. Add r.season to get one row per driver-season.'));
    L.push(season ? 'GROUP BY r.driver, r.season' : 'GROUP BY r.driver');
    if (having.length) {
      L.push(...note('HAVING filters the groups after they are counted, which WHERE cannot do.' + (minStarts > 0 ? ' A rate needs enough starts to mean anything.' : '')));
      L.push('HAVING ' + having.join('\n  AND '));
    }
    L.push(...note(`ORDER BY sorts the rows: ${S.low ? 'lowest first (a lower average finish is better)' : 'biggest first'}, and ties go to the driver with more starts.`));
    L.push(`ORDER BY ${order} ${dir}, COUNT(*) DESC`);
    L.push(...note('LIMIT stops after this many rows.'));
    L.push(`LIMIT ${top}`);
    return {sql: L.join('\n'), spec: spec(o, S, {season, from, to, top, minStarts, exact, tt}), stat: S};
  }

  // The same query as a spec for query/query.html. A rate comes out as a fraction (0-1) there, as the catalog defines it, where the SQL above gives a percentage.
  function spec(o, S, v) {
    const measures = [S.measure, ...EXTRA.map(x => x.measure)].filter((m, i, a) => a.indexOf(m) === i);
    if (!v.season) measures.push('first_season', 'last_season');
    const params = {series: 'Cup', min_season: v.from, max_season: v.to, limit: v.top};
    const s = {
      subject: 'driver_race', params,
      row_filters: [{field: 'series', op: '=', param: 'series'}, {field: 'season', op: '>=', param: 'min_season'}, {field: 'season', op: '<=', param: 'max_season'}],
      group_by: v.season ? ['driver', 'season'] : ['driver'], measures,
      sort: [{by: S.measure, dir: S.low ? 'asc' : 'desc'}, ...(S.measure === 'starts' ? [] : [{by: 'starts', dir: 'desc'}])],
      limit: {param: 'limit'},
    };
    if (v.tt) s.row_filters.push({field: 'track_type', op: '=', value: v.tt});
    if (S.rate) { params.min_starts = v.minStarts; s.qualifier = {name: 'min_starts'}; }
    if (v.exact !== null) { params.wins = v.exact; s.aggregate_filters = [{measure: 'wins', op: '=', param: 'wins'}]; }
    return s;
  }

  // A link that opens the spec in the builder (query.html reads #spec=<base64url JSON>). `base` is where the query server is.
  function builderUrl(spec, base) {
    const json = typeof Buffer !== 'undefined' ? Buffer.from(JSON.stringify(spec), 'utf8').toString('base64') : btoa(unescape(encodeURIComponent(JSON.stringify(spec))));
    return `${base || 'http://127.0.0.1:8765/query/query.html'}#spec=${json.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')}`;
  }

  return {STATS, leaders, builderUrl};
})();
if (typeof module !== 'undefined') module.exports = NASCARSql;
