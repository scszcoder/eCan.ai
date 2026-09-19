// Behavioural check for __ecanSidebarShape, against hand-built fake rows.
//
// The question it has to answer correctly is the one that cost us two
// incidents: when Feige rebuilds the sidebar and stops emitting the hook a
// parser depends on, does the fingerprint move? And — just as important —
// when Feige merely re-hashes its class names on a routine deploy, does the
// fingerprint stay still, so the permanent record does not fill up with noise?
//
// No browser, no network. Reads the JS the app actually ships.

const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
eval(src);   // defines __ecanSidebarShape

let failures = 0;
function check(name, cond, detail) {
  if (cond) { console.log('  ok   ' + name); }
  else { failures++; console.log('  FAIL ' + name + (detail ? ' — ' + detail : '')); }
}

// ── a minimal element stand-in ─────────────────────────────────────────────
function el(tag, attrs, kids) {
  const a = attrs || {};
  const node = {
    tagName: tag.toUpperCase(),
    className: a.class || '',
    attributes: Object.keys(a).map((k) => ({ name: k, value: a[k] })),
    _kids: kids || [],
    getAttribute: (k) => (k in a ? a[k] : null),
    get textContent() { return (node._kids || []).map((k) => k.textContent).join(''); },
  };
  return node;
}

function descendants(node) {
  let out = [];
  for (const k of node._kids || []) { out.push(k); out = out.concat(descendants(k)); }
  return out;
}

function row(kids) {
  const r = el('div', { class: 'conversationItem' }, kids);
  const all = descendants(r);
  r.querySelectorAll = function (sel) {
    if (sel === '*') return all;
    return all.filter((kid) => matches(kid, sel));
  };
  r.querySelector = function (sel) { return this.querySelectorAll(sel)[0] || null; };
  return r;
}

function matches(kid, sel) {
  const a = {};
  for (const at of kid.attributes) a[at.name] = at.value;
  const cls = a.class || '';
  switch (sel) {
    case '[data-qa-id="qa-conversation-nickname"]':
      return a['data-qa-id'] === 'qa-conversation-nickname';
    case '[data-qa-id*="nickname" i],[data-qa-id*="name" i]':
      return /nickname|name/i.test(a['data-qa-id'] || '');
    case '[class*="nameLine"]':          return cls.includes('nameLine');
    case '[class*="NameContent"]':       return cls.includes('NameContent');
    case '[title]':                      return 'title' in a;
    case '.MP1bk3ccfHC9V2SnPCGD':        return cls.includes('MP1bk3ccfHC9V2SnPCGD');
    case '.Jv6FtqUv5VoYARd2pp4y':        return cls.includes('Jv6FtqUv5VoYARd2pp4y');
    case '[class*="msgContent"]':        return cls.includes('msgContent');
    case '[class*="badge-count"]':       return cls.includes('badge-count');
    case 'sup':                          return kid.tagName === 'SUP';
    case '[class*="userLabel"]':         return cls.includes('userLabel');
    case '[class*="cardTag"]':           return cls.includes('cardTag');
    default: return false;
  }
}

// ── the two layouts that actually happened ─────────────────────────────────

// Before: the machine identifier is emitted, and the parser keys on it.
const oldRow = row([
  el('span', { 'data-qa-id': 'qa-conversation-nickname', title: 'Alice' }),
  el('div',  { class: 'nameLine MP1bk3ccfHC9V2SnPCGD', title: 'Alice' }),
  el('div',  { class: 'msgContent aBcDeF1234567890Gh' }),
  el('sup',  {}),
]);

// After (the September rebuild): no data-qa-id anywhere, hashed wrapper gone.
const newRow = row([
  el('div',  { class: 'nameLine', title: 'Alice' }),
  el('div',  { class: 'msgContent zZyYxX9876543210Ww' }),
  el('sup',  {}),
]);

// A routine redeploy: same structure, freshly rotated build hashes.
const rehashedRow = row([
  el('span', { 'data-qa-id': 'qa-conversation-nickname', title: 'Alice' }),
  el('div',  { class: 'nameLine MP1bk3ccfHC9V2SnPCGD', title: 'Alice' }),
  el('div',  { class: 'msgContent qQwWeErRtTyY55667788' }),
  el('sup',  {}),
]);

console.log('__ecanSidebarShape:');

const before = __ecanSidebarShape([oldRow]);
const after = __ecanSidebarShape([newRow]);
const rehashed = __ecanSidebarShape([rehashedRow]);

check('the anchor a parser depends on is seen while it exists',
      before.anchors_present.includes('data_qa_id_nickname'));

check('and is reported missing once the site stops emitting it',
      after.anchors_missing.includes('data_qa_id_nickname') &&
      !after.anchors_present.includes('data_qa_id_nickname'));

check('a vanished legacy wrapper is caught too',
      before.anchors_present.includes('legacy_hashed_wrap') &&
      after.anchors_missing.includes('legacy_hashed_wrap'));

check('the data-qa-id VALUE is kept — it is a stable machine id, not content',
      before.attributes.includes('data-qa-id=qa-conversation-nickname'),
      JSON.stringify(before.attributes));

// The structural record must ignore a hash rotation; the deploy marker must
// notice it. That split is the whole point of having two keys.
function structural(shape) {
  const copy = Object.assign({}, shape);
  delete copy.build_marker;
  return JSON.stringify(copy);
}

check('a routine hash rotation is NOT a structural change',
      structural(before) === structural(rehashed),
      'noise would fill the permanent record on every deploy');

check('but the deploy marker DOES move on a hash rotation',
      before.build_marker && rehashed.build_marker &&
      before.build_marker.digest !== rehashed.build_marker.digest,
      'without this there is no way to know when the site ships');

check('the same build gives the same marker',
      __ecanSidebarShape([oldRow]).build_marker.digest ===
      __ecanSidebarShape([oldRow]).build_marker.digest);

check('the marker is a digest, not the tokens',
      !JSON.stringify(before.build_marker).includes('MP1bk3ccfHC9V2SnPCGD') &&
      before.build_marker.digest.length <= 8);

// Which rows happen to be scrolled into view must not move the marker, or it
// would report a deploy several times an hour.
const manySame = [];
for (let i = 0; i < 12; i++) manySame.push(oldRow);
check('sampling more rows of the same build does not move the marker',
      __ecanSidebarShape(manySame).build_marker.digest ===
      before.build_marker.digest);

check('a build with no hashed classes reports no marker rather than a fake one',
      __ecanSidebarShape([row([el('div', { class: 'plain' })])]).build_marker === null);

check('no build hash is recorded verbatim',
      !JSON.stringify(before).includes('MP1bk3ccfHC9V2SnPCGD') &&
      !JSON.stringify(before).includes('aBcDeF1234567890Gh'));

check('hashed classes are counted in buckets instead',
      typeof before.hashed_class_count_bucket === 'string' &&
      before.hashed_class_count_bucket === rehashed.hashed_class_count_bucket);

// ── it must never carry customer text ──────────────────────────────────────
const nosy = row([
  el('span', { 'data-qa-id': 'qa-conversation-nickname',
               title: 'Alice Chen', 'aria-label': 'order 8891 is late' }),
]);
const nosyShape = JSON.stringify(__ecanSidebarShape([nosy]));
check('no attribute VALUE other than data-qa-id travels',
      !nosyShape.includes('Alice Chen') && !nosyShape.includes('order 8891'),
      nosyShape);
check('but the attribute NAMES do',
      nosyShape.includes('aria-label') && nosyShape.includes('title'));

// ── it must survive a page we do not control ───────────────────────────────
check('junk rows do not throw', (() => {
  try { __ecanSidebarShape([null, undefined, 42, {}, 'nope']); return true; }
  catch (e) { return false; }
})());

check('an empty sidebar does not throw', (() => {
  try { __ecanSidebarShape([]); __ecanSidebarShape(null); return true; }
  catch (e) { return false; }
})());

check('a row whose DOM walk explodes is skipped, not fatal', (() => {
  const hostile = { querySelector: () => { throw new Error('boom'); },
                    querySelectorAll: () => { throw new Error('boom'); } };
  try { __ecanSidebarShape([hostile, oldRow]); return true; }
  catch (e) { return false; }
})());

console.log(failures ? `\n${failures} failure(s)` : '\nall passed');
process.exit(failures ? 1 : 0);
