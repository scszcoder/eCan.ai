// Run a chip-docs collector script (an `async (arg) => {...}` expression, as evaluate_to_file runs it) under
// Node: node run_collector.js <script.js> <page url the browser would be on> [args JSON] [out.json]
// Provides DOMParser (jsdom) and location; fetch is Node's own. Sites that need a real browser (cookies,
// bot checks, CORS-restricted APIs) must be tested in Chrome instead.
const fs = require('fs');
const {JSDOM} = require(require('path').join(__dirname, '../../gui_v2/node_modules/jsdom'));
const [script, page, argJson, out] = process.argv.slice(2);
global.DOMParser = class { parseFromString(t) { return new JSDOM(t).window.document; } };
global.location = new URL(page);
const fn = eval(fs.readFileSync(script, 'utf8'));
fn(argJson ? JSON.parse(argJson) : undefined).then(r => {
  const s = JSON.stringify(r, null, 1);
  if (out) fs.writeFileSync(out, s);
  console.log(Array.isArray(r) ? `${r.length} rows` : `total ${r && r.total}`);
  console.log(s.slice(0, 3000));
}).catch(e => { console.log('ERROR', e.message); process.exit(1); });
