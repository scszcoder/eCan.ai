#!/usr/bin/env node
/**
 * Local smoke tests — no real DB required.
 *
 * Boots an in-process HTTP server with a mocked PrismaClient and walks the
 * primary GraphQL operations (Query / Mutation / Subscription) plus a real
 * subscription round-trip through the event-bus (the same path the SSE bridge
 * uses to deliver events to subscribers).
 *
 * Usage: node scripts/smoke-test-local.js
 */

const http = require('node:http');
const { createYoga, createSchema } = require('graphql-yoga');
const { subscribe, parse } = require('graphql');
const bus = require('../event-bus');

// ---- Mock PrismaClient ----
const FAKE_DB = {};
function makeModelStore(model) {
  if (!FAKE_DB[model]) FAKE_DB[model] = { rows: new Map(), auto: 0 };
  return FAKE_DB[model];
}
const mockPrisma = new Proxy({}, {
  get: (_, model) => {
    if (model === '$connect') return async () => {};
    if (model === '$disconnect') return async () => {};
    if (model === '$isConnected') return () => true;
    if (model === '$queryRaw') return async () => [{ ok: 1 }];
    if (model === '$transaction') return async (ops) => Promise.all(ops);
    const store = makeModelStore(model);
    return new Proxy({}, {
      get: (_, op) => async (args) => {
        const where = (args && args.where) || {};
        const data = (args && args.data) || {};
        const create = (args && args.create) || {};
        const update = (args && args.update) || {};
        const include = (args && args.include) || {};
        if (op === 'create') {
          const id = data.id || `mock-${model}-${++store.auto}`;
          const row = { ...data, id };  // id after spread so it never gets overridden
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
          if (where.OR) {
            rows = rows.filter(r => where.OR.some(clause =>
              Object.entries(clause).every(([k, v]) => {
                if (typeof v === 'object' && v && 'contains' in v) return String(r[k] || '').includes(String(v.contains));
                return String(r[k]) === String(v);
              })
            ));
          } else {
            rows = rows.filter(r => Object.entries(where).every(([k, v]) => {
              if (typeof v === 'object' && v && 'contains' in v) return String(r[k] || '').includes(String(v.contains));
              return String(r[k]) === String(v);
            }));
          }
          return rows.map(r => {
            const out = { ...r };
            for (const inc of Object.keys(include)) out[inc] = [];
            return out;
          });
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
        if (op === 'count') return store.rows.size;
        return {};
      }
    });
  }
});

// ---- Build schema ----
process.env.DATABASE_URL = 'postgresql://mock:mock@localhost:5432/test';
process.env.ALLOW_INSECURE_AUTH = 'true';
process.env.NODE_ENV = 'test';
process.env.PRISMA_POOL_SIZE = '2';
require('@prisma/client').PrismaClient = function () { return mockPrisma; };
delete require.cache[require.resolve('../tcb-init')];
const resolvers = require('../resolvers');
const fs = require('fs');

const idx = fs.readFileSync(require.resolve('../index.js'), 'utf8');
const typeDefs = idx.match(/const typeDefs = `([\s\S]*?)`;/)[1];
const schema = createSchema({ typeDefs, resolvers });

const yoga = createYoga({
  schema,
  graphqlEndpoint: '/api/graphql',
  landingPage: true,
  context: async () => ({
    prisma: mockPrisma,
    identity: { sub: 'u1' },
    getScheduler: () => ({}),
  }),
  fetchAPI: { Response },
});

// ---- HTTP helper ----
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

// ---- Main ----
async function run() {
  const PORT = 9876;
  const httpServer = http.createServer(async (req, res) => {
    const url = new URL(req.url, `http://localhost:${PORT}`);
    let bodyBuf;
    if (['POST', 'PUT', 'PATCH'].includes(req.method)) {
      bodyBuf = await new Promise((r) => {
        let d = '';
        req.on('data', (c) => (d += c));
        req.on('end', () => r(d));
      });
    }
    const request = new Request(url, {
      method: req.method,
      headers: req.headers,
      body: bodyBuf,
    });
    const response = await yoga.fetch(request);
    res.writeHead(response.status, Object.fromEntries(response.headers.entries()));
    res.end(await response.text());
  });

  await new Promise((r) => httpServer.listen(PORT, r));
  console.log(`✓ Server listening on http://localhost:${PORT}\n`);

  let passed = 0;
  let failed = 0;
  function check(name, cond) {
    if (cond) { console.log(`  ✓ ${name}`); passed++; }
    else { console.error(`  ✗ FAIL: ${name}`); failed++; }
  }

  try {
    // 1. GET landing page
    const landing = await httpRequest({ host: 'localhost', port: PORT, path: '/api/graphql', method: 'GET' });
    check('GET /graphql returns 200', landing.status === 200);

    // 2. POST introspection
    const intro = await httpRequest(
      { host: 'localhost', port: PORT, path: '/api/graphql', method: 'POST', headers: { 'content-type': 'application/json' } },
      JSON.stringify({ query: '{ __schema { queryType { name } mutationType { name } subscriptionType { name } } }' })
    );
    const schemaInfo = JSON.parse(intro.body);
    check('Introspection works', intro.status === 200 && !schemaInfo.errors);
    check('Has query type', schemaInfo?.data?.__schema?.queryType?.name === 'Query');
    check('Has mutation type', schemaInfo?.data?.__schema?.mutationType?.name === 'Mutation');
    check('Has subscription type', schemaInfo?.data?.__schema?.subscriptionType?.name === 'Subscription');

    // 3. addAgents mutation
    const addResp = await httpRequest(
      { host: 'localhost', port: PORT, path: '/api/graphql', method: 'POST', headers: { 'content-type': 'application/json' } },
      JSON.stringify({ query: 'mutation { addAgents(input: [{ name: "smoke-test-agent" }]) { id success } }' })
    );
    const addData = JSON.parse(addResp.body);
    check('addAgents mutation returns 200', addResp.status === 200);
    check('addAgents has no errors', !addData.errors);
    if (addData.errors) console.error('  addErrors:', JSON.stringify(addData.errors, null, 2));
    check('addAgents returns id', addData?.data?.addAgents?.[0]?.id != null);
    console.log('  addAgents result:', JSON.stringify(addData?.data?.addAgents));

    // 4. getAgents query (with the newly created agent)
    const getResp = await httpRequest(
      { host: 'localhost', port: PORT, path: '/api/graphql', method: 'POST', headers: { 'content-type': 'application/json' } },
      JSON.stringify({ query: '{ getAgents { id name status } }' })
    );
    const getData = JSON.parse(getResp.body);
    check('getAgents query returns 200', getResp.status === 200);
    check('getAgents has no errors', !getData.errors);
    if (getData.errors) console.error('  getErrors:', JSON.stringify(getData.errors, null, 2));

    // 5. getSkillEditorEvents
    const eventsResp = await httpRequest(
      { host: 'localhost', port: PORT, path: '/api/graphql', method: 'POST', headers: { 'content-type': 'application/json' } },
      JSON.stringify({ query: '{ getSkillEditorEvents(sessionId: "sess-X") { eventId eventType } }' })
    );
    check('getSkillEditorEvents returns 200', eventsResp.status === 200);

    // 6. publishSkillEditorStreamEvent triggers EventBus
    const publishResp = await httpRequest(
      { host: 'localhost', port: PORT, path: '/api/graphql', method: 'POST', headers: { 'content-type': 'application/json' } },
      JSON.stringify({ query: 'mutation { publishSkillEditorStreamEvent(input: { sessionId: "sess-WS-1", eventType: "node-enter", payload: { node: "start" } }) { eventId eventType } }' })
    );
    check('publishSkillEditorStreamEvent returns 200', publishResp.status === 200);

    // 7. Subscription via graphql.subscribe (SSE in production; graphql-yoga's
    //    subscribe path is what runs server-side when an SSE client connects).
    console.log('\n  Testing subscription...');
    const subQuery = `subscription { onSkillEditorStreamEvent(sessionId: "sess-WS-2") { eventId eventType } }`;
    const subResult = await subscribe({
      schema,
      document: parse(subQuery),
      contextValue: { prisma: mockPrisma, identity: { sub: 'u1' } },
    });

    setImmediate(() => {
      bus.publish('onSkillEditorStreamEvent', 'sess-WS-2', {
        eventId: 'ws-evt-1', eventType: 'test-event', sessionId: 'sess-WS-2',
      });
    });

    const subNext = await Promise.race([
      subResult.next(),
      new Promise((_, r) => setTimeout(() => r(new Error('WS_TIMEOUT')), 3000)),
    ]);
    check('WS subscription receives event', !subNext.done && subNext.value?.data?.onSkillEditorStreamEvent?.eventId === 'ws-evt-1');
    await subResult.return();

    // 8. Bus metrics
    check('Bus cleaned up after subscription', bus.metrics().channels === 0);

    // 9. PreStop hook
    const { disconnect } = require('../tcb-init');
    await disconnect();
    check('Prisma disconnect runs without error', true);

    // ============================================================
    // P2.8 round-trips: mutation → event-bus → subscription
    // ============================================================
    console.log('\n  Testing P2.8 publish mutations...');

    /**
     * Round-trip helper.
     *
     * Uses `bus.subscribe` directly to avoid the race in `graphql.subscribe`'s
     * async iterator wrapping. The resolver at `resolvers/subscriptions.js`
     * uses `bus.subscribe` under the hood, so this exercises the exact code
     * path the GraphQL subscription would. Step 7 above additionally validates
     * the full `graphql.subscribe` pipeline end-to-end.
     *
     * Note: graphql-yoga wraps subscription iterators with `mapAsyncIterator`,
     * so a small async hop is expected. We therefore race `bus.next()` against
     * a 3s timeout.
     */
    async function roundTrip({ name, query, subscription }) {
      const { topic, target, payloadAssert } = subscription;
      // Subscription field arg extractor — keep in sync with resolvers/subscriptions.js
      const extractors = {
        onPuzzleReceived: () => '__global__',
        onPuzzleResultReceived: (a) => a.pzid,
        onLongLLMTaskComplete: (a) => a.id,
        onStoryUpdate: (a) => a.acctSiteID,
        onSceneComplete: (a) => a.request_id,
        onAgentSceneEvent: (a) => a.acctSiteID,
      };
      const iter = bus.subscribe(topic, extractors[topic]({ acctSiteID: target, request_id: target, id: target, pzid: target }), { prisma: mockPrisma, identity: { sub: 'u1' } });
      try {
        const resp = await httpRequest(
          { host: 'localhost', port: PORT, path: '/api/graphql', method: 'POST', headers: { 'content-type': 'application/json' } },
          JSON.stringify({ query })
        );
        check(`${name}: mutation returns 200`, resp.status === 200);
        const next = await Promise.race([
          iter.next(),
          new Promise((_, r) => setTimeout(() => r({ done: true }), 3000)),
        ]);
        check(`${name}: subscription receives payload`, !next.done && payloadAssert(next.value));
      } finally {
        await iter.return();
      }
    }

    // Keep `roundTripLazy` around as an alias in case a flaky resolver
    // needs an extra event-loop hop (currently unused).
    async function roundTripLazy(args) { return roundTrip(args); }

    await roundTrip({
      name: 'publishPuzzle → onPuzzleReceived',
      query: `mutation { publishPuzzle(input: { pzid: "puz-1", type: "captcha", question: "1+1" }) { pzid type } }`,
      subscription: {
        topic: 'onPuzzleReceived',
        target: '__global__',
        payloadAssert: (v) => v && v.pzid === 'puz-1' && v.type === 'captcha',
      },
    });

    await roundTrip({
      name: 'publishPuzzleResult → onPuzzleResultReceived',
      query: `mutation { publishPuzzleResult(input: { pzid: "puz-1", result: "2", solver: "me" }) { pzid solver result } }`,
      subscription: {
        topic: 'onPuzzleResultReceived',
        target: 'puz-1',
        payloadAssert: (v) => v && v.pzid === 'puz-1' && v.result === '2',
      },
    });

    await roundTrip({
      name: 'publishLongLLMTaskComplete → onLongLLMTaskComplete',
      query: `mutation { publishLongLLMTaskComplete(input: { id: "task-99", acctSiteID: "site-A", status: "complete", results: "{}" }) { id status } }`,
      subscription: {
        topic: 'onLongLLMTaskComplete',
        target: 'site-A',
        payloadAssert: (v) => v && v.id === 'task-99' && v.status === 'complete',
      },
    });

    await roundTrip({
      name: 'publishStoryUpdate → onStoryUpdate',
      query: `mutation { publishStoryUpdate(input: { id: "story-1", acctSiteID: "site-A", title: "Hello", status: active }) { id title status } }`,
      subscription: {
        topic: 'onStoryUpdate',
        target: 'site-A',
        payloadAssert: (v) => v && v.id === 'story-1' && v.title === 'Hello',
      },
    });

    await roundTrip({
      name: 'publishSceneComplete → onSceneComplete',
      query: `mutation { publishSceneComplete(input: { request_id: "req-7", scene_id: "sc-1", acctSiteID: "site-A", agent_ids: ["a1"], status: completed }) { request_id scene_id status } }`,
      subscription: {
        topic: 'onSceneComplete',
        target: 'site-A',
        payloadAssert: (v) => v && v.request_id === 'req-7' && v.status === 'completed',
      },
    });

    await roundTrip({
      name: 'publishAgentSceneEvent → onAgentSceneEvent',
      query: `mutation { publishAgentSceneEvent(input: { request_id: "req-8", scene_id: "sc-2", acctSiteID: "site-B", agent_ids: ["a2"], status: completed }) { request_id scene_id } }`,
      subscription: {
        topic: 'onAgentSceneEvent',
        target: 'site-B',
        payloadAssert: (v) => v && v.request_id === 'req-8' && v.acctSiteID === 'site-B',
      },
    });

    // Final cleanup check
    check('Bus cleaned up after P2.8 round-trips', bus.metrics().channels === 0);

  } catch (e) {
    console.error('Runner error:', e);
    failed++;
  }

  await new Promise((r) => httpServer.close(r));

  console.log(`\n${'='.repeat(40)}`);
  console.log(`Results: ${passed} passed, ${failed} failed`);
  console.log('='.repeat(40));
  process.exit(failed > 0 ? 1 : 0);
}

run().catch((e) => { console.error('Fatal:', e); process.exit(1); });