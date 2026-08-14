/**
 * Health check for the SCF container.
 *
 * For Liveness (HTTP 200 readiness):
 *   - module availability (prisma, graphql, cos)
 *   - env-var presence
 *
 * For Readiness (real DB ping) we attempt a `SELECT 1` with a 2-second ceiling.
 * A transient DB outage returns 503, NOT 500 — operators can tell the difference.
 */

const crypto = require('node:crypto');
const { prismaPing } = require('./tcb-init');

function generateRandomSecret() {
  return crypto.randomBytes(32).toString('hex');
}

function moduleChecks() {
  const checks = {};
  for (const [name, dep] of [
    ['prisma', '@prisma/client'],
    ['graphql', 'graphql'],
    ['cos', 'cos-nodejs-sdk-v5'],
  ]) {
    try { require(dep); checks[name] = true; }
    catch (e) { checks[name] = { error: e.message }; }
  }
  return checks;
}

exports.health = async () => {
  const db = await prismaPing(2000);
  const body = {
    timestamp: new Date().toISOString(),
    environment: {
      NODE_ENV: process.env.NODE_ENV || 'not set',
      TCB_REGION: process.env.TCB_REGION || 'not set',
      DATABASE_URL: process.env.DATABASE_URL ? 'set (masked)' : 'not set',
      COS_BUCKET: process.env.COS_BUCKET || 'not set',
      COS_REGION: process.env.COS_REGION || 'not set',
    },
    node: {
      version: process.version,
      platform: process.platform,
      arch: process.arch,
    },
    modules: moduleChecks(),
    database: db,
    randomSecret: generateRandomSecret(),
  };
  // 503 lets load-balancers / SCF readiness probes distinguish "container up but DB dead"
  // from "container is alive and reachable".
  const status = db.ok || !process.env.DATABASE_URL ? 200 : 503;
  return {
    statusCode: status,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body, null, 2),
  };
};

exports.main = exports.health;