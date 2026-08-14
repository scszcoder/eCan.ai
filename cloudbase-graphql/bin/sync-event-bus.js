#!/usr/bin/env node
/**
 * sync-event-bus.js — keep cloudbase-graphql/scf/event-bus.js and
 * cloudbase-graphql/ws/event-bus.js byte-identical.
 *
 * Why: ws/index.js loads event-bus via path.resolve(__dirname, 'event-bus')
 * when the WS container is running, and falls back to
 * path.resolve(__dirname, '../scf/event-bus') when running locally. The
 * two copies must be identical because the in-process bus only matters
 * when SCF and WS share a process — in production they're independent
 * processes bridged by HTTP. If the copies drift, a publish in SCF
 * won't be observable by a subscribe in WS, and vice versa.
 *
 * Runs in CI / pre-commit. Fails loudly (exit 1) on drift so neither
 * copy can be silently updated alone.
 *
 * Usage:
 *   node scripts/sync-event-bus.js           # verify (exit 1 on drift)
 *   node scripts/sync-event-bus.js --fix     # copy SCF -> WS to repair
 *
 * The script lives at cloudbase-graphql/bin/ so it can resolve paths
 * relative to the repo root regardless of cwd.
 */
'use strict';

const fs = require('node:fs');
const path = require('node:path');

const SCRIPT_DIR = __dirname;
const REPO_ROOT = path.resolve(SCRIPT_DIR, '..');
const SCF_BUS = path.join(REPO_ROOT, 'scf', 'event-bus.js');
const WS_BUS = path.join(REPO_ROOT, 'ws', 'event-bus.js');

function readOrDie(p) {
  try {
    return fs.readFileSync(p);
  } catch (e) {
    console.error(`❌ Cannot read ${p}: ${e.message}`);
    process.exit(2);
  }
}

const scf = readOrDie(SCF_BUS);
const ws = readOrDie(WS_BUS);

if (Buffer.compare(scf, ws) === 0) {
  console.log(`✓ event-bus in sync (${scf.length} bytes)`);
  process.exit(0);
}

console.error(`❌ event-bus drift:`);
console.error(`   scf: ${SCF_BUS} (${scf.length} bytes, sha256=${require('node:crypto').createHash('sha256').update(scf).digest('hex').slice(0, 12)})`);
console.error(`   ws:  ${WS_BUS}  (${ws.length} bytes, sha256=${require('node:crypto').createHash('sha256').update(ws).digest('hex').slice(0, 12)})`);

if (process.argv.includes('--fix')) {
  fs.writeFileSync(WS_BUS, scf);
  console.error(`   ↳ --fix: copied scf → ws`);
  process.exit(0);
}

console.error(`\nRun with --fix to copy scf/event-bus.js → ws/event-bus.js`);
process.exit(1);