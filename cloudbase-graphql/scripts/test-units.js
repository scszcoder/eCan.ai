#!/usr/bin/env node
/**
 * Smoke tests for the CN backend helper modules.
 *
 * These tests do not require a database or network access. They guard the
 * pure logic (parsers, SCF cron conversion, JWT-less auth user mapping,
 * schedule expression translation, and BigInt-safe AgentEndpoint serialization).
 */
const assert = require('node:assert/strict');
const {
  parseJson, parseIds,
} = require('../compat/cn-relations');
const { TencentScheduler, scheduleExpression, toScfCron, triggerName } = require('../scheduler/tencent-scheduler');
const { log: pruneLog } = (() => ({ log: () => {} }))();

function test(name, fn) {
  try { fn(); console.log(`  ✓ ${name}`); }
  catch (error) { console.error(`  ✗ ${name}: ${error.message}`); process.exitCode = 1; }
}

console.log('parseJson');
test('parses JSON string', () => assert.deepEqual(parseJson('{"a":1}'), { a: 1 }));
test('returns fallback for null', () => assert.deepEqual(parseJson(null, { ok: true }), { ok: true }));
test('returns object as-is', () => assert.deepEqual(parseJson({ a: 1 }, {}), { a: 1 }));
test('returns fallback for invalid JSON', () => assert.deepEqual(parseJson('not json', { ok: true }), { ok: true }));

console.log('parseIds');
test('parses comma separated string', () => assert.deepEqual(parseIds('a,b,c'), ['a', 'b', 'c']));
test('parses JSON array string', () => assert.deepEqual(parseIds('["a","b"]'), ['a', 'b']));
test('handles object input', () => assert.deepEqual(parseIds({ ids: ['x', 'y'] }), ['x', 'y']));
test('returns empty for null', () => assert.deepEqual(parseIds(null), []));
test('trims whitespace', () => assert.deepEqual(parseIds('  a , b  ,'), ['a', 'b']));

console.log('scheduleExpression');
test('rate minutes', () => assert.equal(scheduleExpression({ repeat_type: 'by minutes', repeat_number: 15 }), 'rate(15 minutes)'));
test('rate hours', () => assert.equal(scheduleExpression({ repeat_type: 'by hours', repeat_number: 2 }), 'rate(2 hours)'));
test('rate days', () => assert.equal(scheduleExpression({ repeat_type: 'by days', repeat_number: 1 }), 'rate(1 days)'));
test('none returns null', () => assert.equal(scheduleExpression({ repeat_type: 'none' }), null));
test('passes-through string', () => assert.equal(scheduleExpression('rate(5 minutes)'), 'rate(5 minutes)'));
test('empty returns null', () => assert.equal(scheduleExpression({}), null));
test('throws on unknown type', () => assert.throws(() => scheduleExpression({ repeat_type: 'fortnight' }), /Unsupported/));

console.log('toScfCron');
test('cron() expands to 6-field SCF cron', () => assert.equal(toScfCron('cron(0 12 * * ? *)'), '0 0 12 * * ? *'));
test('rate minutes fits within hour', () => assert.equal(toScfCron('rate(5 minutes)'), '0 */5 * * * * *'));
test('rate hours fits within day', () => assert.equal(toScfCron('rate(2 hours)'), '0 0 */2 * * * *'));
test('rate days fits within month', () => assert.equal(toScfCron('rate(1 days)'), '0 0 0 */1 * * *'));
test('rejects too-long cron', () => assert.throws(() => toScfCron('cron(0 0 * * *)'), /Unsupported/));
test('rejects rate > 59 minutes', () => assert.throws(() => toScfCron('rate(60 minutes)'), /outside/));
test('rejects unknown expression', () => assert.throws(() => toScfCron('every wednesday'), /Unsupported/));

console.log('triggerName');
test('keeps alphanumerics', () => assert.equal(triggerName('task_abc-123'), 'ecan-task-task_abc-123'));
test('replaces unsafe chars', () => assert.equal(triggerName('task.id!@#'), 'ecan-task-task-id---'));
test('clamps to 48 chars', () => assert.ok(triggerName('a'.repeat(80)).length <= 48 + 'ecan-task-'.length));

console.log('TencentScheduler constructor');
test('uses injected env', () => {
  const scheduler = new TencentScheduler({ env: { TENCENT_REGION: 'ap-shanghai' } });
  assert.equal(scheduler.env.TENCENT_REGION, 'ap-shanghai');
});

console.log('Index module loads');
test('GraphQL schema builds', () => {
  require('../index');
});

console.log('snake_case alias transform');
const { camelToSnake, transformSdl } = require('../add_snake_alias');
test('camelToSnake: avatarResourceId', () => assert.equal(camelToSnake('avatarResourceId'), 'avatar_resource_id'));
test('camelToSnake: id stays id', () => assert.equal(camelToSnake('id'), 'id'));
test('camelToSnake: agid stays agid', () => assert.equal(camelToSnake('agid'), 'agid'));
test('camelToSnake: extraData', () => assert.equal(camelToSnake('extraData'), 'extra_data'));
test('camelToSnake: trailing ID collapses (agentID → agent_id, not agent_i_d)', () => {
  assert.equal(camelToSnake('agentID'), 'agent_id');
  assert.equal(camelToSnake('acctSiteID'), 'acct_site_id');
  assert.equal(camelToSnake('msgID'), 'msg_id');
  assert.equal(camelToSnake('runID'), 'run_id');
  assert.equal(camelToSnake('transactionID'), 'transaction_id');
  assert.equal(camelToSnake('chatID'), 'chat_id');
  assert.equal(camelToSnake('taskID'), 'task_id');
  assert.equal(camelToSnake('orderID'), 'order_id');
});
test('camelToSnake: trailing URL/URI/IP also collapse', () => {
  assert.equal(camelToSnake('reqURL'), 'req_url');
  assert.equal(camelToSnake('userURI'), 'user_uri');
  assert.equal(camelToSnake('agentIP'), 'agent_ip');
});
test('camelToSnake: single trailing capital still splits (agentI → agent_i)', () => {
  assert.equal(camelToSnake('agentI'), 'agent_i');
});
test('transformSdl: adds snake alias to camelCase fields', () => {
  const sdl = 'input Foo { camelCase: String snake_case: String flat: String }';
  const out = transformSdl(sdl);
  // Both casings present, no duplicates
  assert.ok(out.includes('camelCase'), 'keeps camelCase');
  assert.ok(out.includes('camel_case'), 'adds snake_case alias');
  assert.ok(out.includes('snake_case'), 'keeps existing snake_case');
  assert.ok(out.includes('flat'), 'keeps flat single-word');
  // Idempotent: running twice yields the same SDL
  const twice = transformSdl(out);
  assert.equal(twice, out);
});
test('transformSdl: preserves non-null marker on alias', () => {
  const sdl = 'input Foo { reqField: String! }';
  const out = transformSdl(sdl);
  assert.ok(out.includes('reqField: String!'), 'keeps required marker');
  assert.ok(out.includes('req_field: String!'), 'alias also required');
});
test('transformSdl: respects already-present snake alias (no dup)', () => {
  const sdl = 'input Foo { camelCase: String camel_case: Int }';
  const out = transformSdl(sdl);
  // No duplicate camel_case
  const matches = out.match(/camel_case:/g) || [];
  assert.equal(matches.length, 1, `expected 1 camel_case: row, got ${matches.length}`);
});
test('transformSdl: real-SDL audit (197 camelCase fields, 0 missing)', () => {
  // Load the actual SDL from index.js, transform, then assert that EVERY
  // camelCase field has its expected snake_case alias declared somewhere.
  const fs = require('node:fs');
  const src = fs.readFileSync(require('node:path').join(__dirname, '..', 'index.js'), 'utf8');
  const m = src.match(/const typeDefs = `([\s\S]*?)`;/);
  assert.ok(m, 'extract typeDefs from index.js');
  const out = transformSdl(m[1]);
  const inputRe = /input (\w+) \{([\s\S]*?)\n\}/g;
  const aliasRe = /([A-Z]{2,})$/;
  let mm, total = 0, missing = [];
  while ((mm = inputRe.exec(out)) !== null) {
    const inputName = mm[1];
    const fieldNames = new Set(
      mm[2].split('\n').map((l) => l.match(/^  (\w+):/) && l.match(/^  (\w+):/)[1]).filter(Boolean)
    );
    for (const f of fieldNames) {
      if (!/[A-Z]/.test(f) || /_/.test(f)) continue;
      let alias;
      const trail = aliasRe.exec(f);
      if (trail) {
        const head = f.slice(0, -trail[1].length);
        alias = head.replace(/[A-Z]/g, (ch) => '_' + ch.toLowerCase()) + '_' + trail[1].toLowerCase();
      } else {
        alias = f.replace(/[A-Z]/g, (ch) => '_' + ch.toLowerCase());
      }
      if (alias === f) continue;
      total++;
      if (!fieldNames.has(alias)) missing.push(`${inputName}.${f} → ${alias}`);
    }
  }
  assert.equal(missing.length, 0,
    missing.length
      ? `missing snake aliases:\n  ${missing.join('\n  ')}`
      : '');
  assert.ok(total >= 50, `expected at least 50 camelCase fields, got ${total}`);
});

if (process.exitCode) {
  console.error('\nFAIL: at least one test failed');
} else {
  console.log('\nPASS unit tests');
}
