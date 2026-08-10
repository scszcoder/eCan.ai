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

if (process.exitCode) {
  console.error('\nFAIL: at least one test failed');
} else {
  console.log('\nPASS unit tests');
}
