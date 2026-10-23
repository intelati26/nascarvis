// node tests/check_shards.js <files-mode dashboard.html> <single-file dashboard.html>
// Loads the season files written next to the first HTML, merges them with shards.js, and requires the
// result to equal the data embedded in the second (single-file) HTML.
const assert = require('assert'), fs = require('fs'), path = require('path');
const NV = require('../shards.js');
const [filesHtml, singleHtml] = process.argv.slice(2);
const dir = path.join(path.dirname(filesHtml), 'dashboard_data');

const html = fs.readFileSync(filesHtml, 'utf8');
assert(!/const D = \{/.test(html), 'files-mode HTML must not embed the data');
const run = f => new Function('NV', fs.readFileSync(path.join(dir, f), 'utf8'))(NV);
run('manifest.js');
const m = JSON.parse(fs.readFileSync(path.join(dir, 'manifest.js'), 'utf8').replace(/^NV\.manifest\(/, '').replace(/\);\s*$/, ''));
for (const s of m.shards) run(s.file);
const merged = NV.build();

const single = fs.readFileSync(singleHtml, 'utf8');
const a = single.indexOf('const D = ') + 'const D = '.length, b = single.indexOf(';\n"use strict"');
const embedded = JSON.parse(single.slice(a, b));

assert.deepStrictEqual(merged, embedded);
assert.deepStrictEqual(m.shards.map(s => s.season), [...new Set(embedded.season)]);
console.log('shards OK:', m.shards.length, 'seasons,', embedded.season.length, 'rows, merged data equals embedded data');
