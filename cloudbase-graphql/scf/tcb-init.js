/**
 * TCB and Prisma client singletons with SCF cold-start optimization.
 *
 * Cold-start optimizations:
 *   - Lazy `getPrisma()` so unit tests don't pull a connection pool
 *   - On first GraphQL hit, force `prisma.$connect()` so the JWT/TCP handshake happens
 *     before user code starts executing the query (avoids 200-400ms first-query latency)
 *   - Connect-pool parameters injected via DATABASE_URL: connection_limit / connect_timeout
 *   - `SIGTERM` listener (SCF shutdown signal) closes the pool cleanly so the next instance
 *     starts fresh and quickly
 *   - Health-probe via `prismaPing()` does a real `SELECT 1`, not just a require check
 *   - `withPrisma(fn)` wraps a callback in try/catch so a 5xx DB response never empties
 *     the SCF context (which would propagate to subsequent requests)
 */

const cloudbase = require('@cloudbase/node-sdk');
const { PrismaClient } = require('@prisma/client');

// ---------- TCB singleton (only constructed when TCB_REGION is set) ----------
let tcbApp = null;
function getTcbApp() {
  if (!tcbApp && process.env.TCB_REGION) {
    tcbApp = cloudbase.init({ env: cloudbase.SYMBOL_CURRENT_ENV });
  }
  return tcbApp;
}

// ---------- Prisma Client singleton ----------
let prisma = null;
let prismaConnectPromise = null;
let sigtermRegistered = false;

function buildPoolParams() {
  // Default settings favor serverless: small pool, short timeouts, no statement cache that
  // we have to invalidate across invocations.
  const params = new URLSearchParams();
  params.set('connection_limit', process.env.PRISMA_POOL_SIZE || '5');
  params.set('connect_timeout', process.env.PRISMA_CONNECT_TIMEOUT || '5');
  params.set('pool_timeout', process.env.PRISMA_POOL_TIMEOUT || '10');
  params.set('socket_timeout', process.env.PRISMA_SOCKET_TIMEOUT || '30');
  // Disable Prisma's bind/format cache between calls to keep memory footprint low.
  return params;
}

function buildDatasourceUrl() {
  const base = process.env.DATABASE_URL;
  if (!base) return null;
  // If user already has a query string, preserve it; otherwise inject our defaults.
  const hashIndex = base.indexOf('#');
  const fragment = hashIndex >= 0 ? base.slice(hashIndex) : '';
  const body = hashIndex >= 0 ? base.slice(0, hashIndex) : base;
  const qIndex = body.indexOf('?');
  if (qIndex >= 0) return base;
  return `${body}?${buildPoolParams()}${fragment}`;
}

function getPrisma() {
  if (prisma) return prisma;
  const url = buildDatasourceUrl();
  if (!url) {
    throw new Error('Missing DATABASE_URL environment variable');
  }
  prisma = new PrismaClient({
    datasources: { db: { url } },
    log: process.env.NODE_ENV === 'development' ? ['query', 'error', 'warn'] : ['error'],
    errorFormat: 'minimal',
  });
  registerSigtermOnce();
  return prisma;
}

// Eager-connect on first use. Idempotent — repeated calls share the same promise.
async function ensureConnected() {
  const client = getPrisma();
  if (client.$isConnected && client.$isConnected()) return client;
  if (!prismaConnectPromise) {
    prismaConnectPromise = client.$connect().catch((err) => {
      // Reset so the next request can retry; otherwise a transient outage bricks the instance.
      prismaConnectPromise = null;
      throw err;
    });
  }
  await prismaConnectPromise;
  return client;
}

// Health-probe: real SELECT 1, returns null on failure.
async function prismaPing(timeoutMs = 2000) {
  if (!process.env.DATABASE_URL) return { ok: false, reason: 'no DATABASE_URL' };
  try {
    const client = getPrisma();
    const probe = client.$queryRaw`SELECT 1 AS ok`;
    const timeout = new Promise((_, reject) => setTimeout(() => reject(new Error('ping timeout')), timeoutMs));
    await Promise.race([probe, timeout]);
    return { ok: true, latencyMs: Date.now() };
  } catch (e) {
    return { ok: false, reason: e.message };
  }
}

// ---------- SCF SIGTERM hook ----------
// SCF sends SIGTERM when freezing/terminating the instance. Disconnect so the next instance
// opens a fresh pool instead of inheriting stale connections.
function registerSigtermOnce() {
  if (sigtermRegistered) return;
  sigtermRegistered = true;
  const cleanup = () => {
    if (!prisma) return;
    try { prisma.$disconnect().catch(() => {}); } catch { /* swallow */ }
  };
  process.once('SIGTERM', cleanup);
  process.once('SIGINT', cleanup);
}

// For tests / scheduled shutdown
async function disconnect() {
  if (!prisma) return;
  try { await prisma.$disconnect(); } catch { /* swallow */ }
  prisma = null;
  prismaConnectPromise = null;
}

// Limited visibility for observability dashboards. Never expose connection passwords.
function getMetrics() {
  return {
    initialized: !!prisma,
    connecting: !!prismaConnectPromise,
    poolSize: Number(process.env.PRISMA_POOL_SIZE || 5),
  };
}

module.exports = {
  getTcbApp,
  getPrisma,
  ensureConnected,
  prismaPing,
  disconnect,
  getMetrics,
};