#!/usr/bin/env node
/**
 * Smoke tests for the CN backend helper modules.
 *
 * These tests do not require a database or network access. They guard the
 * pure logic (parsers, SCF cron conversion, JWT-less auth user mapping,
 * schedule expression translation, and BigInt-safe AgentEndpoint serialization).
 */
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
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

console.log('skill tag filters');
const { tagFilter } = require('../resolvers/entities')._test;
test('all tags use PostgreSQL JSON array containment', () => {
  assert.deepEqual(tagFilter(['a', 'b'], 'all'), { tags: { array_contains: ['a', 'b'] } });
});
test('any tags use one JSON containment branch per tag', () => {
  assert.deepEqual(tagFilter(['a', 'b'], 'any'), {
    OR: [
      { tags: { array_contains: ['a'] } },
      { tags: { array_contains: ['b'] } },
    ],
  });
});

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

console.log('prompt snapshots');
const { promptRevisionKey, promptSnapshotKey, requirePromptCosConfig } = require('../storage/prompt-snapshots');
test('builds an owner-scoped prompt snapshot key', () => {
  assert.equal(
    promptSnapshotKey('user/name@example.com', 'prompt/1', {}),
    'ecan-prompts/user_name@example.com/prompt_1.json',
  );
});
test('supports a dedicated physical prompt bucket', () => {
  assert.deepEqual(requirePromptCosConfig({
    PROMPTS_COS_BUCKET: 'ecan-prompts-1251680599',
    PROMPTS_COS_REGION: 'ap-shanghai',
  }), { bucket: 'ecan-prompts-1251680599', region: 'ap-shanghai' });
});
test('builds an immutable fallback revision key', () => {
  assert.equal(
    promptRevisionKey('user@example.com', 'prompt-1', { updatedAt: new Date('2026-08-16T01:02:03.456Z') }, {}, 'abc123'),
    'ecan-prompts/user@example.com/prompt-1/versions/2026-08-16T01_02_03.456Z-abc123.json',
  );
});
test('uploads a JSON prompt snapshot and returns its COS version', () => {
  const script = `
    const { savePromptSnapshot } = require('./storage/prompt-snapshots');
    const calls = [];
    const client = { putObject(params, callback) { calls.push(params); callback(null, { VersionId: 'v2', ETag: 'etag-1' }); } };
    savePromptSnapshot({
      id: 'prompt-1', owner: 'user@example.com', prompt: { title: 'Test' }, version: '1',
      createdAt: new Date('2026-08-16T00:00:00Z'), updatedAt: new Date('2026-08-16T00:01:00Z'),
    }, { client, env: { COS_BUCKET: 'base-1251680599', COS_REGION: 'ap-shanghai' } }).then(result => {
      const request = calls[0];
      const body = JSON.parse(request.Body);
      if (request.Key !== 'ecan-prompts/user@example.com/prompt-1.json') process.exit(1);
      if (request.ContentType !== 'application/json; charset=utf-8') process.exit(1);
      if (body.prompt.title !== 'Test' || result.versionId !== 'v2') process.exit(1);
    }).catch(() => process.exit(1));
  `;
  execFileSync(process.execPath, ['-e', script], { cwd: require('node:path').join(__dirname, '..') });
});
test('writes an immutable revision when COS bucket versioning is disabled', () => {
  const script = `
    const { savePromptSnapshot } = require('./storage/prompt-snapshots');
    const calls = [];
    const client = { putObject(params, callback) { calls.push(params); callback(null, { ETag: 'etag-1' }); } };
    savePromptSnapshot({
      id: 'prompt-1', owner: 'user@example.com', prompt: { title: 'Test' }, version: '1',
      createdAt: new Date('2026-08-16T00:00:00Z'), updatedAt: new Date('2026-08-16T00:01:00Z'),
    }, { client, env: { COS_BUCKET: 'base-1251680599', COS_REGION: 'ap-shanghai' } }).then(result => {
      if (calls.length !== 2) process.exit(1);
      const prefix = 'ecan-prompts/user@example.com/prompt-1/versions/2026-08-16T00_01_00.000Z-';
      if (!calls[1].Key.startsWith(prefix) || !/^[a-f0-9]{12}\.json$/.test(calls[1].Key.slice(prefix.length))) process.exit(1);
      if (result.revisionKey !== calls[1].Key || result.versionId !== null) process.exit(1);
    }).catch(() => process.exit(1));
  `;
  execFileSync(process.execPath, ['-e', script], { cwd: require('node:path').join(__dirname, '..') });
});
test('reads and parses a prompt snapshot from COS', () => {
  const script = `
    const { getPromptSnapshot } = require('./storage/prompt-snapshots');
    const client = { getObject(params, callback) {
      callback(null, { Body: Buffer.from(JSON.stringify({ id: 'prompt-1', prompt: { title: 'Saved' } })), VersionId: 'v3', ETag: 'etag-2' });
    } };
    getPromptSnapshot('user@example.com', 'prompt-1', {
      client, env: { COS_BUCKET: 'base-1251680599', COS_REGION: 'ap-shanghai' },
    }).then(result => {
      if (result.key !== 'ecan-prompts/user@example.com/prompt-1.json') process.exit(1);
      if (result.snapshot.prompt.title !== 'Saved' || result.versionId !== 'v3') process.exit(1);
      if (result.contentLength < 1) process.exit(1);
    }).catch(() => process.exit(1));
  `;
  execFileSync(process.execPath, ['-e', script], { cwd: require('node:path').join(__dirname, '..') });
});
test('lists immutable prompt revisions from COS', () => {
  const script = `
    const { listPromptRevisions } = require('./storage/prompt-snapshots');
    const client = { getBucket(params, callback) {
      callback(null, { Contents: [{ Key: params.Prefix + 'v1.json', Size: '123', ETag: 'etag-3' }] });
    } };
    listPromptRevisions('user@example.com', 'prompt-1', {
      client, env: { COS_BUCKET: 'base-1251680599', COS_REGION: 'ap-shanghai' },
    }).then(result => {
      if (result.prefix !== 'ecan-prompts/user@example.com/prompt-1/versions/') process.exit(1);
      if (result.revisions[0].size !== 123 || !result.revisions[0].key.endsWith('v1.json')) process.exit(1);
    }).catch(() => process.exit(1));
  `;
  execFileSync(process.execPath, ['-e', script], { cwd: require('node:path').join(__dirname, '..') });
});

console.log('account compatibility');
const { queryAccounts, queryMine, saveAccounts } = require('../compat/cn-accounts');
test('account compatibility uses owner-scoped accounts and cnbus queries', async () => {
  const calls = [];
  const prisma = {
    $queryRawUnsafe: async (sql, ...values) => {
      calls.push({ sql, values });
      if (sql.startsWith('INSERT')) return [{ actid: 8 }];
      if (sql.includes('FROM accounts')) return [{ actid: 8, user_name: 'user-1', fund: '4', quota: '2', last_actions: {} }];
      if (sql.includes('FROM cnbus')) return [{ bid: 3, actid: 8, orderid: 'order-1', unitprice: '9', discounttype: '', dealtype: '', paymethod: '' }];
      return [];
    },
  };
  const identity = { sub: 'user-1' };
  assert.deepEqual(JSON.parse(await saveAccounts(prisma, identity, [{ actid: '0', email: 'u@example.com' }])), [{ id: '8', success: true }]);
  assert.equal(calls[0].values[0], 'user-1');
  assert.equal(calls[0].values.includes('u@example.com'), true);
  assert.equal(JSON.parse(await queryAccounts(prisma, identity, [{ actid: '8' }]))[0].actid, '8');
  assert.deepEqual(calls[1].values, [8, 'user-1']);
  const mine = await queryMine(prisma, identity);
  assert.equal(mine.acctInfo.actid, '8');
  assert.equal(mine.ordersInfo[0].BID, '3');
  assert.equal(calls[3].sql.includes('cnbus'), true);
});

console.log('Index module loads');
test('GraphQL schema builds', () => {
  require('../index');
});

// --- auth.js header reader regression (2026-08-13) ---
//
// `request.headers` arriving from the SCF gateway wrapper
// (`new Headers(event.headers)`) is a `Headers` instance, NOT a `Map`. The
// pre-fix resolver only checked `instanceof Map` and then fell through to
// bare property access — both of which return `undefined` on a `Headers`
// object — so the SCF path always errored with "Bearer token required".
// These tests lock the multi-shape reader in place so the regression cannot
// silently reappear.
console.log('auth._readHeader');
const { _readHeader, directTestHeaders } = require('../auth');
test('direct test mode is disabled by default', () => {
  assert.throws(() => directTestHeaders('user-1'), /disabled/);
});
test('direct test mode maps an internally proven owner', () => {
  const script = `
    const { directTestHeaders, resolveIdentity } = require('./auth');
    const request = { headers: new Headers(directTestHeaders('user-1')) };
    resolveIdentity(request).then(identity => {
      if (identity.sub !== 'user-1') process.exit(1);
    });
  `;
  execFileSync(process.execPath, ['-e', script], {
    cwd: require('node:path').join(__dirname, '..'),
    env: { ...process.env, TCB_DIRECT_TEST_MODE: 'true' },
  });
});
test('HTTP test mode requires the configured secret', () => {
  const script = `
    const { resolveIdentity } = require('./auth');
    const owner = 'http-test-user';
    const good = { headers: new Headers({
      'x-ecan-http-test-owner': owner,
      'x-ecan-http-test-secret': process.env.TCB_HTTP_TEST_SECRET,
    }) };
    const bad = { headers: new Headers({
      'x-ecan-http-test-owner': owner,
      'x-ecan-http-test-secret': 'wrong-secret',
    }) };
    Promise.all([
      resolveIdentity(good).then(identity => {
        if (identity.sub !== owner) process.exit(1);
      }),
      resolveIdentity(bad).then(() => process.exit(1), error => {
        if (!/Bearer token required/.test(error.message)) process.exit(1);
      }),
    ]);
  `;
  execFileSync(process.execPath, ['-e', script], {
    cwd: require('node:path').join(__dirname, '..'),
    env: {
      ...process.env,
      TCB_DIRECT_TEST_MODE: 'true',
      TCB_HTTP_TEST_MODE: 'true',
      TCB_HTTP_TEST_SECRET: 'unit-test-secret-at-least-32-bytes-long',
    },
  });
});
test('HTTP test route reaches Yoga and rejects missing credentials', () => {
  const script = `
    const { main } = require('./index');
    const event = {
      path: '/',
      httpMethod: 'POST',
      headers: {
        host: 'test.local',
        'content-type': 'application/json',
        'x-ecan-http-test-owner': 'http-test-user',
        'x-ecan-http-test-secret': process.env.TCB_HTTP_TEST_SECRET,
      },
      body: JSON.stringify({ query: '{ __typename }' }),
    };
    Promise.all([
      main(event, {}).then(response => {
        const body = JSON.parse(response.body);
        if (response.statusCode !== 200 || body.data?.__typename !== 'Query') process.exit(1);
      }),
      main({ ...event, headers: { host: 'test.local', 'content-type': 'application/json' } }, {})
        .then(response => {
          const body = JSON.parse(response.body);
          if (body.errors?.[0]?.extensions?.code !== 'UNAUTHENTICATED') process.exit(1);
        }),
    ]);
  `;
  const env = { ...process.env };
  delete env.DATABASE_URL;
  execFileSync(process.execPath, ['-e', script], {
    cwd: require('node:path').join(__dirname, '..'),
    env: {
      ...env,
      TCB_DIRECT_TEST_MODE: 'true',
      TCB_HTTP_TEST_MODE: 'true',
      TCB_HTTP_TEST_SECRET: 'unit-test-secret-at-least-32-bytes-long',
    },
  });
});
test('auth._readHeader: Headers shape (production SCF path)', () => {
  const h = new Headers({ authorization: 'Bearer jwt-a' });
  assert.equal(_readHeader(h, 'authorization'), 'Bearer jwt-a');
});
test('auth._readHeader: Headers with mixed-case original key', () => {
  // `new Headers(...)` lower-cases keys on construction, so this only differs
  // when an object is passed in directly.
  const h = new Headers({ Authorization: 'Bearer jwt-b' });
  assert.equal(_readHeader(h, 'authorization'), 'Bearer jwt-b');
});
test('auth._readHeader: Map shape', () => {
  const m = new Map([['authorization', 'Bearer jwt-c']]);
  assert.equal(_readHeader(m, 'authorization'), 'Bearer jwt-c');
});
test('auth._readHeader: plain object shape', () => {
  assert.equal(_readHeader({ authorization: 'Bearer jwt-d' }, 'authorization'), 'Bearer jwt-d');
  assert.equal(_readHeader({ Authorization: 'Bearer jwt-e' }, 'authorization'), 'Bearer jwt-e');
});
test('auth._readHeader: undefined / empty headers', () => {
  assert.equal(_readHeader(undefined, 'authorization'), '');
  assert.equal(_readHeader(null, 'authorization'), '');
});
test('auth._readHeader: missing key returns empty string', () => {
  assert.equal(_readHeader(new Headers({}), 'authorization'), '');
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

test('transformSdl: also aliases camelCase fields on output ObjectTypes', () => {
  // Regression: the CN cloudbase-graphql SDL has camelCase fields on its
  // output types (e.g. type Agent { supervisorId: String }).  Clients
  // coming from the AppSync (snake_case) world select these with snake
  // names; without output-side aliases, GraphQL validation rejects the
  // selection set with "Cannot query field 'supervisor_id' on type 'Agent'".
  // The transformSdl path must therefore alias both input and output.
  const sdl = 'type Agent { id: ID! supervisorId: String vehicleId: String extraData: JSON }';
  const out = transformSdl(sdl);
  assert.ok(out.includes('supervisorId'), 'keeps camelCase on type');
  assert.ok(out.includes('supervisor_id'), 'adds snake alias on type');
  assert.ok(out.includes('vehicleId') && out.includes('vehicle_id'), 'adds snake alias for vehicleId');
  assert.ok(out.includes('extraData') && out.includes('extra_data'), 'adds snake alias for extraData');
  // Idempotent
  assert.equal(transformSdl(out), out);
});

test('transformSdl: addSnakeAliases aliasTypes option keeps backward-compat toggle', () => {
  const sdl = 'type Agent { supervisorId: String } input Foo { avatarResourceId: String }';
  const { addSnakeAliases } = require('../add_snake_alias');
  const { parse, print } = require('graphql');
  const ast = parse(sdl);

  // Default: type fields ARE aliased now (we expanded scope to support clients
  // that come from the AppSync world).
  const outDefault = print(addSnakeAliases(ast));
  assert.ok(outDefault.includes('supervisor_id'), 'default aliases types');
  assert.ok(outDefault.includes('avatar_resource_id'), 'default aliases inputs');

  // aliasTypes:false — explicitly skip ObjectType (only alias inputs)
  const outInputsOnly = print(addSnakeAliases(parse(sdl), { aliasTypes: false }));
  assert.ok(!outInputsOnly.includes('supervisor_id'), 'aliasTypes:false skips ObjectType');
  assert.ok(outInputsOnly.includes('avatar_resource_id'), 'aliasTypes:false still aliases inputs');
});

if (process.exitCode) {
  console.error('\nFAIL: at least one test failed');
} else {
  console.log('\nPASS unit tests');
}
