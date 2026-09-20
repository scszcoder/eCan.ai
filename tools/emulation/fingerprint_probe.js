// Runs the REAL sidebar fingerprint over a structured row description.
//
// Usage:  node fingerprint_probe.js <shape_js_file> <rows_json_file>
//
// Prints the fingerprint as JSON on stdout. Nothing is ported or reimplemented
// here: the fingerprint source is read from the file the app actually ships, so
// the harness cannot drift from the thing it is measuring — which is the exact
// failure (two copies of one parser) that ROW_NAME_JS was consolidated to stop.
//
// A minimal element stand-in is enough because the fingerprint only ever reads
// tagName, attributes, className and querySelector(All). It never reads text.

const fs = require('fs');

const shapeSrc = fs.readFileSync(process.argv[2], 'utf8');
const rows = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));

eval(shapeSrc);   // defines __ecanSidebarShape

// ── element stand-in ───────────────────────────────────────────────────────

function build(spec) {
  const attrs = Object.assign({}, spec.attributes || {});
  const classes = (spec.classes || []).slice();
  if (classes.length) attrs.class = classes.join(' ');

  const node = {
    tagName: String(spec.tag || 'div').toUpperCase(),
    className: attrs.class || '',
    attributes: Object.keys(attrs).map((k) => ({ name: k, value: attrs[k] })),
    _kids: (spec.children || []).map(build),
    // The fingerprint measures how deep an anchor sits, and the preview reader
    // compares parents, so the stand-in has to model this much of the DOM.
    parentElement: null,
  };
  for (const kid of node._kids) kid.parentElement = node;
  return node;
}

function descendants(node) {
  let out = [];
  for (const k of node._kids || []) { out.push(k); out = out.concat(descendants(k)); }
  return out;
}

function attrsOf(node) {
  const a = {};
  for (const at of node.attributes) a[at.name] = at.value;
  return a;
}

// Only the selector shapes the fingerprint asks for. Anything else returns no
// match, which is the honest answer for a stand-in.
function matches(node, sel) {
  const a = attrsOf(node);
  const cls = a.class || '';
  const has = (frag) => cls.split(/\s+/).some((t) => t.includes(frag));

  switch (sel) {
    case '[data-qa-id="qa-conversation-nickname"]':
      return a['data-qa-id'] === 'qa-conversation-nickname';
    case '[data-qa-id*="nickname" i],[data-qa-id*="name" i]':
      return /nickname|name/i.test(a['data-qa-id'] || '');
    case '[class*="nameLine"]':     return has('nameLine');
    case '[class*="NameContent"]':  return has('NameContent');
    case '[title]':                 return 'title' in a;
    case '.MP1bk3ccfHC9V2SnPCGD':   return has('MP1bk3ccfHC9V2SnPCGD');
    case '.Jv6FtqUv5VoYARd2pp4y':   return has('Jv6FtqUv5VoYARd2pp4y');
    case '[class*="msgContent"]':   return has('msgContent');
    case '[class*="badge-count"]':  return has('badge-count');
    case 'sup':                     return node.tagName === 'SUP';
    case '[class*="userLabel"]':    return has('userLabel');
    case '[class*="cardTag"]':      return has('cardTag');
    default: return false;
  }
}

function asRow(spec) {
  const root = build(spec);
  const all = descendants(root);
  root.querySelectorAll = function (sel) {
    if (sel === '*') return all;
    return all.filter((k) => matches(k, sel));
  };
  root.querySelector = function (sel) { return this.querySelectorAll(sel)[0] || null; };
  return root;
}

const built = rows.map(asRow);
process.stdout.write(JSON.stringify(__ecanSidebarShape(built)));
