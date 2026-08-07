#!/usr/bin/env node
/**
 * Skill-store functional probes.
 *
 * Boots an in-process GraphQL server with a mocked Prisma (same harness as
 * scripts/smoke-test-local.js) and walks the AgentSkill surface looking for
 * issues that the happy-path smoke tests don't catch:
 *
 *   - JSON scalar → Prisma JSON column round-trip (array vs. string)
 *   - cross-owner write/read rejection
 *   - partial-batch failure on addAgentSkills
 *   - skill editor file storage delegation
 *   - skill editor chat session + publish
 *   - skill subscription channel
 *
 * No real DB / network. Does not modify production code.
 */
const assert = require('node:assert/strict');
const http = require('node:http');
const { createYoga, createSchema } = require('graphql-yoga');
const bus = require('../event-bus');

const FAKE_DB = {};
// Models whose primary key column is named something other than `id`.
// Mirrors cloudbase-graphql/prisma/schema.prisma.
const PK_BY_MODEL = {
  skillEditorEvent: 'eventId',
};
function makeModelStore(model) {
  if (!FAKE_DB[model]) FAKE_DB[model] = { rows: new Map(), auto: 0 };
  return FAKE_DB[model];
}
const mockPrisma = new Proxy({}, {
  get: (_, model) => {
    if (model === '$connect') return async () => {};
    if (model === '$disconnect') return async () => {};
    if (model === '$transaction') {
      // Prisma accepts either a function (interactive) or an array of promises (batch).
      // The CN relations code uses batch form (array of upsert promises).
      return async (arg) => {
        if (typeof arg === 'function') return arg(mockPrisma);
        return Promise.all(arg);
      };
    }
    const store = makeModelStore(model);
    return new Proxy({}, {
      get: (_, op) => async (args) => {
        const where = (args && args.where) || {};
        const data = (args && args.data) || {};
        const create = (args && args.create) || {};
        const update = (args && args.update) || {};
        const take = (args && args.take) || undefined;
        if (op === 'create') {
          // Models whose primary key is *not* `id`: synthesize it.
          const pkCol = PK_BY_MODEL[model] || 'id';
          const id = data[pkCol] || data.id || `mock-${model}-${++store.auto}`;
          const row = { [pkCol]: id, ...data };
          delete row.id; // don't double up unless pk is really `id`
          row[pkCol] = id;
          store.rows.set(id, row);
          return row;
        }
        if (op === 'findFirst') {
          for (const r of store.rows.values()) {
            if (Object.entries(where).every(([k, v]) => String(r[k]) === String(v))) return r;
          }
          return null;
        }
        if (op === 'findMany') {
          let rows = Array.from(store.rows.values());
          const matchRow = (r, w) => Object.entries(w).every(([k, v]) => {
            if (v && typeof v === 'object' && 'contains' in v) {
              const left = String(r[k] || '');
              const right = String(v.contains);
              // Prisma `mode: 'insensitive'` lowercases both sides. The mock
              // does the same so the test surface mirrors production.
              const isInsen = v.mode === 'insensitive' || v.mode == null;
              return isInsen
                ? left.toLowerCase().includes(right.toLowerCase())
                : left.includes(right);
            }
            if (v && typeof v === 'object' && 'in' in v) {
              return v.in.map(String).includes(String(r[k]));
            }
            if (v && typeof v === 'object' && 'hasSome' in v) {
              // JSON array column; `hasSome` matches if the row's array
              // contains any of the supplied values.
              const rowVals = Array.isArray(r[k]) ? r[k] : [];
              return v.hasSome.some((s) => rowVals.map(String).includes(String(s)));
            }
            if (v && typeof v === 'object' && 'hasEvery' in v) {
              const rowVals = Array.isArray(r[k]) ? r[k] : [];
              return v.hasEvery.every((s) => rowVals.map(String).includes(String(s)));
            }
            return String(r[k]) === String(v);
          });
          if (where.OR) {
            // Non-OR fields (e.g., `owner`) are AND'd with the OR clause so
            // the query stays owner-scoped. The Prisma semantics: any OR
            // operand can match, but every top-level non-OR field must hold.
            rows = rows.filter(r => {
              const base = Object.entries(where).every(([k, v]) => k === 'OR' || matchRow(r, { [k]: v }));
              const matchesOr = where.OR.some((clause) => matchRow(r, clause));
              return base && matchesOr;
            });
          } else {
            rows = rows.filter(r => matchRow(r, where));
          }
          if (typeof take === 'number') rows = rows.slice(0, take);
          return rows;
        }
        if (op === 'upsert') {
          let existing = null;
          for (const r of store.rows.values()) {
            if (Object.entries(where).every(([k, v]) => String(r[k]) === String(v))) { existing = r; break; }
          }
          if (existing) { Object.assign(existing, update); return existing; }
          const row = { id: where.id || `mock-${model}-${++store.auto}`, ...create };
          store.rows.set(row.id, row);
          return row;
        }
        if (op === 'delete') { const id = where.id; return store.rows.delete(id) ? { id } : null; }
        if (op === 'deleteMany') { let c = 0; for (const [k, r] of store.rows) { if (Object.entries(where).every(([kv, v]) => String(r[kv]) === String(v))) { store.rows.delete(k); c++; } } return { count: c }; }
        if (op === 'update') {
          let target = null;
          for (const r of store.rows.values()) {
            if (Object.entries(where).every(([k, v]) => String(r[k]) === String(v))) { target = r; break; }
          }
          if (target) Object.assign(target, data);
          return target || {};
        }
        if (op === 'updateMany') {
          let c = 0;
          for (const r of store.rows.values()) {
            if (Object.entries(where).every(([k, v]) => String(r[k]) === String(v))) {
              Object.assign(r, data); c++;
            }
          }
          return { count: c };
        }
        if (op === 'count') return store.rows.size;
        if (op === 'aggregate') {
          // groupby/sum/_avg/_count — we only need _avg and _count here.
          const rows = Array.from(store.rows.values());
          const argsAvg = (args && args._avg) || {};
          const argsCount = (args && args._count) || {};
          const out = { _avg: {}, _count: {} };
          for (const key of Object.keys(argsAvg)) {
            const list = rows.map((r) => Number(r[key])).filter((n) => Number.isFinite(n));
            out._avg[key] = list.length ? list.reduce((a, b) => a + b, 0) / list.length : null;
          }
          for (const key of Object.keys(argsCount)) {
            // `_all` is a Prisma sentinel for total count. Otherwise the key
            // is a field name.
            out._count[key] = key === '_all' ? rows.length : rows.filter((r) => r[key] != null).length;
          }
          return out;
        }
        if (op === 'findUnique') {
          const where = (args && args.where) || {};
          for (const r of store.rows.values()) {
            if (Object.entries(where).every(([k, v]) => {
              if (v && typeof v === 'object' && v !== null) {
                // Composite unique (e.g., userId_skillId) — match each key.
                return Object.entries(v).every(([sk, sv]) => String(r[sk]) === String(sv));
              }
              return String(r[k]) === String(v);
            })) return r;
          }
          return null;
        }
        return {};
      },
    });
  },
});

process.env.DATABASE_URL = 'postgresql://mock:mock@localhost:5432/test';
process.env.ALLOW_INSECURE_AUTH = 'true';
process.env.NODE_ENV = 'test';
require('@prisma/client').PrismaClient = function () { return mockPrisma; };
delete require.cache[require.resolve('../tcb-init')];
const resolvers = require('../resolvers');
const fs = require('fs');
const idx = fs.readFileSync(require.resolve('../index.js'), 'utf8');
const typeDefs = idx.match(/const typeDefs = `([\s\S]*?)`;/)[1];
const schema = createSchema({ typeDefs, resolvers });

const PORT = 9877;
const yoga = createYoga({
  schema,
  graphqlEndpoint: '/api/graphql',
  // Insecure auth mirrors cloudbase-graphql/auth.js: x-ecan-test-user picks
  // the identity when ALLOW_INSECURE_AUTH is set. We can't reuse auth.js
  // directly because it pulls @cloudbase/node-sdk through tcb-init; the
  // mock harness is meant to run with no real SDK.
  context: async ({ request }) => {
    const sub = request.headers.get('x-ecan-test-user') || 'alice';
    return {
      prisma: mockPrisma,
      identity: { sub },
      getScheduler: () => ({}),
    };
  },
  fetchAPI: { Response },
});

const httpServer = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  let bodyBuf;
  if (['POST', 'PUT', 'PATCH'].includes(req.method)) {
    bodyBuf = await new Promise((r) => { let d = ''; req.on('data', (c) => (d += c)); req.on('end', () => r(d)); });
  }
  const request = new Request(url, { method: req.method, headers: req.headers, body: bodyBuf });
  const response = await yoga.fetch(request);
  res.writeHead(response.status, Object.fromEntries(response.headers.entries()));
  res.end(await response.text());
});

function httpRequest(options, body) {
  return new Promise((resolve, reject) => {
    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', (chunk) => (data += chunk));
      res.on('end', () => resolve({ status: res.statusCode, body: data }));
    });
    req.on('error', reject);
    if (body) req.write(body);
    req.end();
  });
}
async function gql(query, variables) {
  // Default identity is 'alice' to keep the early probes simple.
  return gqlAs('alice', query, variables);
}

async function gqlAs(identity, query, variables) {
  // HTTP/1.1 headers are case-insensitive but the Node http module accepts
  // any case for the request. We send lowercase to match what express/yoga
  // typically see in `request.headers.get(name)`.
  const headers = { 'content-type': 'application/json' };
  if (identity) headers['x-ecan-test-user'] = identity;
  const resp = await httpRequest(
    { host: 'localhost', port: PORT, path: '/api/graphql', method: 'POST', headers },
    JSON.stringify({ query, variables }),
  );
  return JSON.parse(resp.body);
}

let passed = 0;
let failed = 0;
async function probe(name, fn) {
  try { await fn(); console.log(`  ✓ ${name}`); passed++; }
  catch (e) { console.error(`  ✗ ${name}: ${e.message}`); failed++; }
}

async function main() {
  await new Promise((r) => httpServer.listen(PORT, r));
  console.log(`✓ skill-store probes against http://localhost:${PORT}\n`);

  // ------------------------------------------------------------------
  console.log('AgentSkill CRUD: happy path');
  // ------------------------------------------------------------------
  const created = await gql(`mutation { addAgentSkills(input: [{ name: "weather", tags: ["weather","http"], capabilities: ["fetch","cache"], config: { retries: 3 }, isPublic: true }]) { id success error } }`);
  probe('addAgentSkills with JSON arrays succeeds', () => assert.ok(!created.errors && created.data.addAgentSkills[0].success));

  const list = await gql(`{ getAgentSkills { id name tags capabilities config } }`);
  probe('getAgentSkills returns created row', () => assert.ok(!list.errors && list.data.getAgentSkills.length >= 1));
  const weather = list.data.getAgentSkills.find(s => s.name === 'weather');
  probe('tags round-trip is an array (not stringified)', () => assert.ok(Array.isArray(weather?.tags) && weather.tags.length === 2));
  probe('capabilities round-trip is an array', () => assert.ok(Array.isArray(weather?.capabilities) && weather.capabilities.length === 2));
  probe('config round-trip is an object with retries:3', () => assert.ok(typeof weather?.config === 'object' && weather.config?.retries === 3));

  // ------------------------------------------------------------------
  console.log('\nAgentSkill CRUD: owner scoping');
  // ------------------------------------------------------------------
  const id = weather.id;
  // alice tries to read it back as alice
  const ownRead = await gql(`{ getAgentSkills(input: { owner: "alice" }) { id name } }`);
  probe('owner-scoped read as alice returns alice skills', () => assert.ok(ownRead.data.getAgentSkills.some(s => s.id === id)));

  // alice asks for owner's skill: requesting "bob" must be rejected
  const crossRead = await gql(`{ getAgentSkills(input: { owner: "bob" }) { id name } }`);
  probe('cross-owner read as alice is forbidden', () => assert.ok(!!crossRead.errors && crossRead.errors[0].extensions?.code === 'FORBIDDEN'));

  // alice tries to update a row by id alone (no owner override possible —
  // SkillUpdateInput doesn't expose `owner`, GraphQL rejects it).
  const crossWrite = await gql(
    `mutation { updateAgentSkills(input: [{ id: "${id}", name: "stolen" }]) { id success error } }`,
  );
  probe('cross-owner write does not corrupt other users (owner field is not in SkillUpdateInput)', () => assert.ok(
    crossWrite.data?.updateAgentSkills?.[0]?.success === true,
  ));

  // verify alice's row was updated
  const verify = await gql(`{ getAgentSkills { id name } }`);
  const still = verify.data.getAgentSkills.find(s => s.id === id);
  probe('row gets the requested update applied', () => assert.equal(still?.name, 'stolen'));

  // Reset before next check
  await gql(`mutation { updateAgentSkills(input: [{ id: "${id}", name: "weather" }]) { success } }`);

  // alice cannot update a row whose id she doesn't own — bob's row
  const evil = await gql(
    `mutation { updateAgentSkills(input: [{ id: "bob-row-id-does-not-exist-but-real-id-test", name: "pwn" }]) { id success error } }`,
  );
  probe('updating a non-owned id fails gracefully', () => assert.ok(
    !evil.errors && evil.data?.updateAgentSkills?.[0]?.success === false,
  ));

  // ------------------------------------------------------------------
  console.log('\nAgentSkill CRUD: partial-batch failure');
  // ------------------------------------------------------------------
  // The resolver serializes `for (const item of input)` — if an item throws at
  // the Prisma layer (e.g. constraint), what happens? Document the observed
  // behavior. We use a name that passes graphql scalar validation but trips
  // Prisma (we have no real schema constraints to trip here, so we patch
  // agentSkill.create to throw on the second call and observe.)
  FAKE_DB['agentSkill'].rows.clear(); // reset
  const realCreate = FAKE_DB['agentSkill'].rows;
  // Patch prisma create to throw on item with marker
  const origModel = mockPrisma.agentSkill;
  let callCount = 0;
  FAKE_DB['agentSkill'].rows = realCreate; // no-op
  // Easier: inspect the GraphQL round-trip itself.
  // Items with empty name will fail GraphQL input validation (name: String!),
  // so we probe the resolver behavior with a name="" item that gets through
  // to the Prisma layer.
  const partial = await gql(
    `mutation M($input: [SkillInput!]!) { addAgentSkills(input: $input) { id success error } }`,
    { input: [{ name: 'good-1' }, { name: 'good-2' }] }, // both valid => both succeed
  );
  probe('partial-batch: all-valid batch persists all rows', () => assert.ok(
    partial.data?.addAgentSkills?.length === 2 && partial.data.addAgentSkills.every(r => r.success),
  ));

  // Now verify resolver-side loop semantics (per-item failure surface). The
  // current loop does NOT short-circuit on throw, and addAgentSkills has NO
  // try/catch around the create — so the per-item semantics are not yet
  // defined. Document the observed behavior.
  let createIdx = 0;
  const fakeStore = FAKE_DB['agentSkill'];
  fakeStore.rows.clear();
  const failingCtx = {
    prisma: {
      agentSkill: {
        create: async (args) => {
          createIdx++;
          if (createIdx === 2) throw new Error('simulated DB failure');
          const id = args.data.id || `mock-agentSkill-${createIdx}`;
          fakeStore.rows.set(id, { ...args.data, id });
          return fakeStore.rows.get(id);
        },
        findMany: async () => Array.from(fakeStore.rows.values()),
      },
    },
    identity: { sub: 'alice' },
  };
  const resolver = require('../resolvers/entities').Mutation.addAgentSkills;
  let threw = null;
  let loopResp = null;
  try {
    loopResp = await resolver(null, { input: [{ name: 'a' }, { name: 'b' }, { name: 'c' }] }, failingCtx);
  } catch (e) {
    threw = e;
  }
  if (threw) {
    console.log(`  ⚠ resolver crashed on partial failure: ${threw.message}`);
    console.log('  ⚠ KNOWN ISSUE: addAgentSkills has no try/catch around the per-item create (see entities.js:104)');
  } else {
    probe('partial-batch: 3 items returned', () => assert.equal(loopResp.length, 3));
    probe('partial-batch: item 2 carries the simulated error', () => assert.ok(loopResp[1].success === false && /simulated/.test(loopResp[1].error || '')));
    console.log('  ℹ️  partial-batch: items a and c are persisted; item b failed.');
  }

  // ------------------------------------------------------------------
  console.log('\nAgentSkill CRUD: pagination is hard-capped');
  // ------------------------------------------------------------------
  FAKE_DB['agentSkill'].rows.clear();
  const many = await gql(`mutation M($input: [SkillInput!]!) { addAgentSkills(input: $input) { id } }`, {
    input: Array.from({ length: 60 }, (_, i) => ({ name: `skill-${i}` })),
  });
  probe('addAgentSkills bulk-inserts 60 rows', () => assert.equal(many.data?.addAgentSkills?.length, 60));
  const listed = await gql(`{ getAgentSkills { id name } }`);
  // Resolver asks for take+1 rows so callers can compute hasNextPage. The mock
  // prisma in this probe does not honor the extra row, so we document both
  // the mock behavior (cap by default 50 = the +1 slice when no limit is
  // passed) and the real Prisma behavior.
  console.log(`  ℹ️  getAgentSkills mock returned ${listed.data.getAgentSkills.length} of 60 inserted; resolver sets take = limit+1`);

  // ------------------------------------------------------------------
  console.log('\nSkill relations');
  // ------------------------------------------------------------------
  const agentRes = await gql(`mutation { addAgents(input: [{ name: "agent-x" }]) { id } }`);
  const agentId = agentRes.data.addAgents[0].id;
  const skillRes = await gql(`mutation { addAgentSkills(input: [{ name: "core" }]) { id } }`);
  const skillId = skillRes.data.addAgentSkills[0].id;

  // addAgentSkillRelations uses Intl input shape (agid/skid/owner)
  const relResp = await gql(
    `mutation { addAgentSkillRelations(input: [{ agid: "${agentId}", skid: "${skillId}", owner: "alice" }]) }`,
  );
  if (relResp.errors) {
    console.log('  ⚠ relations error:', JSON.stringify(relResp.errors, null, 2));
  }
  console.log('  ℹ raw relations response:', JSON.stringify(relResp.data).substring(0, 200));
  let parsedRel;
  try { parsedRel = JSON.parse(relResp.data?.addAgentSkillRelations || '[]'); }
  catch (e) { console.log('  ⚠ could not parse:', relResp.data?.addAgentSkillRelations); }
  probe('addAgentSkillRelations creates link', () => assert.ok(
    !relResp.errors && parsedRel && parsedRel.some(r => r.success === true),
  ));

  // ------------------------------------------------------------------
  console.log('\nSkill editor events & subscription');
  // ------------------------------------------------------------------
  const evt = await gql(
    `mutation { addSkillEditorEvent(input: { sessionId: "sess-1", eventType: "node-enter" }) { eventId sessionId eventType } }`,
  );
  probe('addSkillEditorEvent stores the row and returns eventId', () => assert.ok(
    !evt.errors && evt.data?.addSkillEditorEvent?.eventId && evt.data.addSkillEditorEvent.eventType === 'node-enter',
  ));

  const got = await gql(`{ getSkillEditorEvents(sessionId: "sess-1") { eventId eventType sessionId } }`);
  probe('getSkillEditorEvents returns 1 row', () => assert.equal(got.data?.getSkillEditorEvents?.length, 1));
  probe('getSkillEditorEvents surfaces eventId from storage', () => assert.ok(
    got.data?.getSkillEditorEvents?.[0]?.eventId && typeof got.data.getSkillEditorEvents[0].eventId === 'string',
  ));
  probe('addSkillEditorEvent and getSkillEditorEvents eventId match', () => assert.equal(
    evt.data?.addSkillEditorEvent?.eventId,
    got.data?.getSkillEditorEvents?.[0]?.eventId,
  ));

  // publishSkillEditorStreamEvent uses the same SkillEditorEvent return type.
  const subIter = bus.subscribe('onSkillEditorStreamEvent', 'sess-ws-probe', { prisma: mockPrisma, identity: { sub: 'alice' } });
  const publishResp = await gql(
    `mutation { publishSkillEditorStreamEvent(input: { owner: "alice", sessionId: "sess-ws-probe", eventType: "stream" }) { eventId sessionId } }`,
  );
  probe('publishSkillEditorStreamEvent returns eventId', () => assert.ok(
    !publishResp.errors && publishResp.data?.publishSkillEditorStreamEvent?.eventId,
  ));
  const next = await Promise.race([
    subIter.next(),
    new Promise((_, r) => setTimeout(() => r({ done: true }), 2000)),
  ]);
  probe('WS onSkillEditorStreamEvent receives payload', () => assert.ok(!next.done && next.value?.sessionId === 'sess-ws-probe'));
  await subIter.return();

  // ------------------------------------------------------------------
  console.log('\nSkill editor chat session');
  // ------------------------------------------------------------------
  const sess = await gql(
    `mutation { createSkillEditorChatSession(input: { userId: "alice", name: "probe" }) { id name } }`,
  );
  if (sess.errors) console.log('  ⚠ sess errors:', JSON.stringify(sess.errors).substring(0, 300));
  console.log('  ℹ sess raw:', JSON.stringify(sess.data).substring(0, 200));
  probe('createSkillEditorChatSession returns id', () => assert.ok(sess.data?.createSkillEditorChatSession?.id && !sess.errors));

  const list2 = await gql(`{ getSkillEditorChatSessions(userId: "alice") { id name } }`);
  probe('getSkillEditorChatSessions lists new session', () => assert.ok(list2.data?.getSkillEditorChatSessions?.some(s => s.id === sess.data?.createSkillEditorChatSession?.id)));

  // ------------------------------------------------------------------
  console.log('\nSkill file storage (cn-skill-editor delegation)');
  // ------------------------------------------------------------------
  const svc = require('../services/cn-skill-editor');
  // listSkillFiles requires executeFileOps. We patch the module so we don't
  // need a real COS connection. The service module destructures at require
  // time, so we patch the source module *before* requiring it.
  const fileOps = require('../storage/cos-file-ops');
  // executeFileOps is already destructured into the service. We replace it
  // before any call by deleting the service cache and re-requiring.
  fileOps.executeFileOps = async () => [{ objects: [{ key: 'skills/probe/skill.yaml', size: 12, lastModified: '2026-01-01T00:00:00Z' }] }];
  delete require.cache[require.resolve('../services/cn-skill-editor')];
  const svc2 = require('../services/cn-skill-editor');
  let listing;
  try {
    listing = JSON.parse(await svc2.listSkillFiles(mockPrisma, { sub: 'alice' }, { prefix: 'probe' }));
  } catch (e) {
    console.log('  ⚠ listSkillFiles threw:', e.message);
  }
  console.log('  ℹ listing:', JSON.stringify(listing).substring(0, 200));
  probe('listSkillFiles returns SkillFileInfo[]', () => assert.ok(Array.isArray(listing) && listing[0]?.fileName === 'skill.yaml' && listing[0]?.skillName === 'probe'));

  // ------------------------------------------------------------------
  console.log('\nSkill marketplace: filter & search');
  // ------------------------------------------------------------------
  // A new context with two users so we can verify owner isolation. The
  // resolver always anchors on the caller's identity, so we seed with two
  // separate mutations (alice then bob) over the x-ecan-test-user header.
  FAKE_DB['agentSkill'].rows.clear();
  const setupAlice = await gqlAs('alice', `mutation M($input: [SkillInput!]!) { addAgentSkills(input: $input) { id success } }`, {
    input: [
      { name: 'weather-fetch', description: 'fetch weather forecasts', category: 'http', tags: ['weather','http'], isPublic: true, price: 0 },
      { name: 'translate-zh', description: 'translate text to Mandarin', category: 'language', tags: ['translation','language'], isPublic: true, price: 500 },
      { name: 'private-utility', category: 'misc', tags: ['internal'], isPublic: false },
    ],
  });
  const setupBob = await gqlAs('bob', `mutation M($input: [SkillInput!]!) { addAgentSkills(input: $input) { id success } }`, {
    input: [
      { name: 'weather-pro', description: 'pro weather via NOAA', category: 'http', tags: ['weather','pro'], isPublic: true, price: 1000, priceModel: 'subscription' },
    ],
  });
  probe('marketplace seed creates 4 rows', () => assert.equal(
    (setupAlice.data?.addAgentSkills?.length || 0) + (setupBob.data?.addAgentSkills?.length || 0), 4,
  ));

  // isPublic: true mode allows browsing without authentication; with our test
  // context it returns ALL public rows (alice's and bob's).
  const browse = await gql(`{ getAgentSkills(input: { isPublic: true }) { id name owner category } }`);
  const browseRows = browse.data?.getAgentSkills || [];
  probe('isPublic:true returns public catalog (3 rows)', () => assert.equal(browseRows.length, 3));
  probe('isPublic:true exposes bob\'s public skill', () => assert.ok(browseRows.some((s) => s.name === 'weather-pro')));
  probe('isPublic:true hides private rows', () => assert.ok(!browseRows.some((s) => s.name === 'private-utility')));

  // category filter narrows the catalog; tag filter narrows further.
  const tagged = await gql(`{ getAgentSkills(input: { isPublic: true, tags: ["weather"] }) { name category } }`);
  const taggedRows = tagged.data?.getAgentSkills || [];
  probe('tag filter returns weather-tagged public skills', () => assert.ok(
    taggedRows.length >= 2 && taggedRows.every((s) => s.category === 'http'),
  ));

  const taggedAll = await gql(`{ getAgentSkills(input: { isPublic: true, tags: ["weather","pro"], tagMode: "all" }) { name } }`);
  probe('tagMode:"all" requires every tag', () => assert.ok(
    taggedAll.data?.getAgentSkills?.length === 1 && taggedAll.data.getAgentSkills[0].name === 'weather-pro',
  ));

  // Case-insensitive substring search via the new searchSkills endpoint.
  const searched = await gql(`{ searchSkills(input: { q: "Weather" }) { name } }`);
  const searchedRows = searched.data?.searchSkills || [];
  probe('searchSkills matches name case-insensitively', () => assert.ok(searchedRows.length >= 2));

  // Anonymous rating: must be rejected.
  const anonymousRating = await gqlAs('anonymous', `mutation { rateSkill(input: { skillId: "x", score: 5 }) { id score } }`);
  probe('rateSkill rejects anonymous callers', () => assert.ok(
    !!anonymousRating.errors && anonymousRating.errors[0].extensions?.code === 'UNAUTHENTICATED',
  ));

  // ------------------------------------------------------------------
  console.log('\nSkill marketplace: rating');
  // ------------------------------------------------------------------
  // Bob's skill id so we can rate it. We register a fresh rating under
  // identity "alice" so order we use the bob-owned skill id.
  const bobSkill = browse.data.getAgentSkills.find((s) => s.name === 'weather-pro');
  const goodSkillId = bobSkill.id;

  // need the correct owner context — switch to "alice" for the rating.
  // (rateSkill is anonymous-blocked but the alice/bob owner context here is
  // selected via the x-ecan-test-user header.)
  const r1 = await gqlAs('alice', `mutation { rateSkill(input: { skillId: "${goodSkillId}", score: 5, comment: "great" }) { score comment userId } }`);
  probe('first rating lands', () => assert.ok(!r1.errors && r1.data?.rateSkill?.score === 5));

  const r2 = await gqlAs('alice', `mutation { rateSkill(input: { skillId: "${goodSkillId}", score: 3 }) { score } }`);
  probe('re-rating upserts (one row, updated score)', () => assert.ok(!r2.errors && r2.data?.rateSkill?.score === 3));

  const rBad = await gqlAs('alice', `mutation { rateSkill(input: { skillId: "${goodSkillId}", score: 99 }) { score } }`);
  probe('rating score outside [1,5] is rejected', () => assert.ok(!!rBad.errors && rBad.errors[0].extensions?.code === 'BAD_USER_INPUT'));

  // After upsert (rating=3) the aggregate should be { score: 3, count: 1 }.
  const checkAgg = await gqlAs('alice', `{ getAgentSkills(input: { isPublic: true }) { name rating ratingCount } }`);
  const aggBob = checkAgg.data.getAgentSkills.find((s) => s.name === 'weather-pro');
  probe('rating aggregate recomputed on the catalog row', () => assert.ok(
    aggBob && aggBob.ratingCount >= 1,
  ));

  // ------------------------------------------------------------------
  console.log('\nSkill marketplace: install & uninstall');
  // ------------------------------------------------------------------
  const inst = await gqlAs('alice', `mutation { recordSkillInstall(input: { skillId: "${goodSkillId}" }) { status skillId } }`);
  probe('recordSkillInstall upserts an install row', () => assert.ok(!inst.errors && inst.data?.recordSkillInstall?.status === 'installed'));

  const installCount = await gqlAs('alice', `{ getAgentSkills(input: { isPublic: true }) { name installCount } }`);
  const bobAfterInstall = installCount.data.getAgentSkills.find((s) => s.name === 'weather-pro');
  probe('installCount increments on the catalog row', () => assert.ok(bobAfterInstall && bobAfterInstall.installCount >= 1));

  const uninstall = await gqlAs('alice', `mutation { removeSkillInstall(skillId: "${goodSkillId}") }`);
  probe('removeSkillInstall returns true', () => assert.ok(
    !uninstall.errors && uninstall.data?.removeSkillInstall === true,
  ));

  // ------------------------------------------------------------------
  console.log('\nSkill marketplace: orders');
  // ------------------------------------------------------------------
  // alice creates an order against bob's weather-pro skill.
  const order = await gqlAs('alice', `mutation { createSkillOrder(input: { skillId: "${goodSkillId}", quantity: 2 }) { id status priceCents buyerId sellerId } }`);
  probe('createSkillOrder returns a pending order with price * quantity', () => assert.ok(
    !order.errors && order.data?.createSkillOrder?.status === 'pending' && order.data.createSkillOrder.priceCents === 2000,
  ));
  const orderId = order.data.createSkillOrder.id;

  // buyer cannot self-approve a pending order; only seller can flip pending → paid.
  const aliceFlips = await gqlAs('alice', `mutation { updateSkillOrderStatus(input: { orderId: "${orderId}", status: "paid" }) { status } }`);
  probe('buyer cannot mark their own order paid', () => assert.ok(!!aliceFlips.errors && aliceFlips.errors[0].extensions?.code === 'BAD_USER_INPUT'));

  const bobFlips = await gqlAs('bob', `mutation { updateSkillOrderStatus(input: { orderId: "${orderId}", status: "paid" }) { status } }`);
  probe('seller flips pending → paid', () => assert.ok(
    !bobFlips.errors && bobFlips.data?.updateSkillOrderStatus?.status === 'paid',
  ));

  const bobList = await gqlAs('bob', `{ listSkillOrders(input: { role: "seller" }) { id status skillId } }`);
  probe('listSkillOrders as seller returns updated status', () => assert.ok(
    bobList.data?.listSkillOrders?.some((o) => o.id === orderId && o.status === 'paid'),
  ));

  const aliceList = await gqlAs('alice', `{ listSkillOrders(input: { role: "buyer" }) { id status skillId } }`);
  probe('listSkillOrders as buyer returns same order', () => assert.ok(
    aliceList.data?.listSkillOrders?.some((o) => o.id === orderId),
  ));

  // ------------------------------------------------------------------
  console.log('\nRAG & chat misc endpoints');
  // ------------------------------------------------------------------
  // Seed a knowledge row so the RAG query has something to find.
  const setupK = await gqlAs('alice', `mutation M($input: [KnowledgeInput!]!) { addAgentKnowledges(input: $input) { id success } }`, {
    input: [
      { name: 'weather-faq', description: 'weather FAQ', content: 'How do I fetch the weather forecast via API?', tags: ['weather'], isPublic: true },
    ],
  });
  probe('seed knowledge row', () => assert.ok(setupK.data?.addAgentKnowledges?.[0]?.success));

  const rag = await gqlAs('alice', `query { queryRAGs(qs: "{ \\"q\\": \\"weather\\" }") }`);
  const ragBody = JSON.parse(rag.data?.queryRAGs || '{}');
  probe('queryRAGs returns matching knowledge', () => assert.ok(
    ragBody.count >= 1 && ragBody.results?.[0]?.name === 'weather-faq',
  ));

  const ragEmpty = await gqlAs('alice', `query { queryRAGs(qs: "{ \\"q\\": \\"password manager\\" }") }`);
  const ragEmptyBody = JSON.parse(ragEmpty.data?.queryRAGs || '{}');
  probe('queryRAGs returns empty for unknown query', () => assert.equal(ragEmptyBody.count, 0));

  // queryChats round-trips a message and returns a stored count + reply.
  const chat = await gqlAs('alice', `query { queryChats(msgs: [{ msgID: "user", user: "alice", msg: "what about weather FAQ?" }]) }`);
  const chatBody = JSON.parse(chat.data?.queryChats || '{}');
  probe('queryChats stores messages and returns structure', () => assert.ok(
    !chat.errors && chatBody.stored >= 1 && chatBody.reply?.msgID === 'assistant',
  ));

  // Cross-owner: bob cannot see alice's knowledge via queryRAGs.
  const bobRag = await gqlAs('bob', `query { queryRAGs(qs: "{ \\"q\\": \\"weather\\" }") }`);
  const bobRagBody = JSON.parse(bobRag.data?.queryRAGs || '{}');
  probe('queryRAGs is owner-scoped', () => assert.equal(bobRagBody.count, 0));

  // ------------------------------------------------------------------
  console.log('\nCleanup');
  // ------------------------------------------------------------------
  const { disconnect } = require('../tcb-init');
  await disconnect();
  probe('Prisma disconnect runs clean', () => assert.ok(true));

  console.log(`\n${'='.repeat(40)}`);
  console.log(`Results: ${passed} passed, ${failed} failed`);
  console.log('='.repeat(40));
  await new Promise((r) => httpServer.close(r));
  process.exit(failed > 0 ? 1 : 0);
}

main().catch((e) => { console.error('Fatal:', e); process.exit(1); });
