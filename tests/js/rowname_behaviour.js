// Behavioural check for the tagged __ecanRowName: every branch must return
// exactly what it returned before tagging, and tag itself exactly once.
// Runs against hand-built fake rows — no browser, no network.

const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');

global.window = {};
eval(src.replace(/var __drain = [\s\S]*$/, ''));   // define __ecanRowName only

// Minimal element stand-in: enough querySelector/getAttribute for the cascade.
function el(opts) {
  const o = Object.assign({ attrs: {}, text: '', kids: [] }, opts);
  return {
    _o: o,
    getAttribute: (k) => (k in o.attrs ? o.attrs[k] : null),
    get textContent() { return o.text; },
    querySelector(sel) { return (this.querySelectorAll(sel) || [])[0] || null; },
    querySelectorAll(sel) {
      // Only the shapes the cascade actually asks for.
      const match = (kid) => {
        const a = kid._o.attrs;
        if (sel === '[data-qa-id="qa-conversation-nickname"]')
          return a['data-qa-id'] === 'qa-conversation-nickname';
        if (sel === '[class*="nameLine"]') return (a.class || '').includes('nameLine');
        if (sel === '[class*="NameContent"]') return (a.class || '').includes('NameContent');
        if (sel === '[data-qa-id*="nickname" i],[data-qa-id*="name" i]')
          return /nickname|name/i.test(a['data-qa-id'] || '');
        if (sel === '[title]') return 'title' in a;
        if (sel === '.MP1bk3ccfHC9V2SnPCGD') return (a.class || '').includes('MP1bk3ccfHC9V2SnPCGD');
        if (sel === '.Jv6FtqUv5VoYARd2pp4y') return (a.class || '').includes('Jv6FtqUv5VoYARd2pp4y');
        return false;
      };
      return o.kids.filter(match);
    },
  };
}

const cases = [
  ['data_qa_id_nickname', 'Alice',
   el({ kids: [el({ attrs: { 'data-qa-id': 'qa-conversation-nickname' }, text: 'Alice' })] })],

  ['name_line_title', 'Bob',
   el({ kids: [el({ attrs: { class: 'x nameLine y', title: 'Bob' } })] })],

  ['name_content', 'Carol',
   el({ kids: [el({ attrs: { class: 'NameContent' }, text: 'Carol' })] })],

  ['ws110_fuzzy_qa_id', 'Dave',
   el({ kids: [el({ attrs: { 'data-qa-id': 'conv-nickname-v2' }, text: 'Dave' })] })],

  // ws183: first [title] is the unread badge; the real name comes later.
  ['ws183_titled_scan', 'Erin',
   el({ kids: [el({ attrs: { title: '1' } }), el({ attrs: { title: 'Erin' } })] })],

  // NOTE: the legacy wrap reads getAttribute('title'), but ws183's titled
  // scan runs FIRST and accepts any short non-numeric title — so a row that
  // would satisfy the wrap branch is always caught earlier. The wrap branch
  // is effectively unreachable. Asserted here so the fact is recorded, and
  // the live counter will confirm it (expect 0 hits).
  ['ws183_titled_scan', 'Frank',
   el({ kids: [el({ attrs: { class: 'MP1bk3ccfHC9V2SnPCGD', title: 'Frank' } })] })],

  ['legacy_hashed_span', 'Grace',
   el({ kids: [el({ attrs: { class: 'Jv6FtqUv5VoYARd2pp4y' }, text: 'Grace' })] })],

  ['unresolved', '', el({ kids: [] })],
];

let failures = 0;
for (const [expectStrategy, expectName, row] of cases) {
  window.__ecanRowNameTally = {};
  const got = __ecanRowName(row);
  const tally = window.__ecanRowNameTally;
  const strategy = Object.keys(tally)[0];
  const tagCount = Object.values(tally).reduce((a, b) => a + b, 0);

  const nameOk = got === expectName;
  const stratOk = strategy === expectStrategy;
  const onceOk = tagCount === 1;
  if (!(nameOk && stratOk && onceOk)) {
    failures++;
    console.log(`FAIL ${expectStrategy}: name=${JSON.stringify(got)} ` +
                `(want ${JSON.stringify(expectName)}) strategy=${strategy} tags=${tagCount}`);
  } else {
    console.log(`ok   ${expectStrategy.padEnd(22)} -> ${JSON.stringify(got)}`);
  }
}

// A null/!querySelector row must still return '' and must NOT tag.
window.__ecanRowNameTally = {};
const nullish = __ecanRowName(null);
if (nullish !== '' || Object.keys(window.__ecanRowNameTally).length !== 0) {
  failures++;
  console.log('FAIL null row: returned', JSON.stringify(nullish),
              'tally', window.__ecanRowNameTally);
} else {
  console.log('ok   null row             -> "" (untagged, as before)');
}

// Tagging must survive a hostile page that froze the global.
window.__ecanRowNameTally = Object.freeze({});
const frozen = __ecanRowName(cases[0][2]);
console.log(frozen === 'Alice'
  ? 'ok   frozen tally           -> name still returned'
  : (failures++, 'FAIL frozen tally broke the return value'));

console.log(failures ? `\n${failures} FAILURE(S)` : '\nall behavioural checks passed');
process.exit(failures ? 1 : 0);
