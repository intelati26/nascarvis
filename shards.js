// Season data shards for the dashboard. Pure functions, no DOM: inlined into the dashboard by
// build_dashboard.py and unit-tested under node (tests/test_shards.py).
//
// build_dashboard.py writes one script file per season (dashboard_data/season-YYYY.js, each calling
// NV.shard(season, {...})) plus manifest.js (NV.manifest({...})). Script tags work when the page is
// opened straight from a folder (file://), where fetch() would be blocked. NV.build() puts the shards
// back together into the same columnar object `D` that the dashboard has always used.
//
// A shard is self-contained: its dictionary columns (drivers, tracks, ...) hold only the strings used
// that season and its index columns point into them, so adding a season never changes another
// season's file.
const NV = (function () {
  // dictionary list -> the per-row index column that points into it
  const DICTS = { drivers: 'driver', tracks: 'track', names: 'name', makes: 'make',
                  teams: 'team', statuses: 'status', surfaces: 'surface' };
  // plain per-row columns
  const COLS = ['season', 'race', 'car', 'length', 'start', 'finish', 'pts', 'laps', 'led',
                's1', 's2', 's3', 'rating', 'win'];

  let manifest = null;
  const shards = new Map();

  // <script> tags for every shard, in season order, for document.write() right after manifest.js.
  function tags(dir) {
    return manifest.shards.map(s =>
      '<script src="' + dir + '/' + s.file + '?v=' + s.v + '"><\/script>').join('');
  }

  function merge(m, shardMap) {
    const order = m.shards.map(s => s.season);
    for (const s of order) {
      if (!shardMap.has(s)) throw new Error('season ' + s + ' did not load (is its file in the data folder?)');
    }
    const out = { title: m.title, adjustments: m.adjustments, lapFiles: m.lapFiles };
    for (const c of COLS) out[c] = [];
    for (const [dk, ik] of Object.entries(DICTS)) {
      // one global dictionary, sorted, as the single-file build has always had
      const all = new Set();
      for (const s of order) for (const v of shardMap.get(s)[dk]) all.add(v);
      const vals = [...all].sort();
      const idx = new Map(vals.map((v, i) => [v, i]));
      out[dk] = vals;
      out[ik] = [];
      for (const s of order) {
        const sh = shardMap.get(s);
        const local = sh[dk].map(v => idx.get(v));
        for (const i of sh[ik]) out[ik].push(local[i]);
      }
    }
    for (const c of COLS) {
      for (const s of order) { const a = shardMap.get(s)[c]; for (let i = 0; i < a.length; i++) out[c].push(a[i]); }
    }
    return out;
  }

  return {
    DICTS, COLS, merge, tags,
    manifest: m => { manifest = m; },
    shard: (season, data) => { shards.set(season, data); },
    build: () => merge(manifest, shards),
  };
})();
if (typeof module !== 'undefined') module.exports = NV;
