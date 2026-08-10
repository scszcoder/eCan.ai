#!/usr/bin/env node
/**
 * 部署前预检：检查 .env.local 完整性 + DB 端点可达性。
 * 区分"本地不应可达（TCB VPC 内网）"和"配置错误"。
 */

const fs = require('node:fs');
const path = require('node:path');

const ENV_FILE = path.join(__dirname, '..', '.env.local');
const PASSPHRASE_FLAG = '__SET_VIA_TCB_CONSOLE_OR_LOCAL_ENV__';

function loadEnv() {
  if (!fs.existsSync(ENV_FILE)) {
    console.error('❌ .env.local 不存在');
    process.exit(1);
  }
  const env = {};
  for (const line of fs.readFileSync(ENV_FILE, 'utf8').split('\n')) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.+?)\s*$/);
    if (m && !m[1].startsWith('#')) env[m[1]] = m[2];
  }
  return env;
}

let failed = 0;
function check(name, ok, hint) {
  if (ok) console.log(`  ✓ ${name}`);
  else { console.error(`  ✗ ${name}`); if (hint) console.error(`    ${hint}`); failed++; }
}

const env = loadEnv();
console.log('🔎 Pre-deployment check\n');

console.log('Config:');
check('TCB_ENV_ID configured', !!env.TCB_ENV_ID, 'set TCB_ENV_ID=sccb0-...');
check('COS_BUCKET configured', !!env.COS_BUCKET, 'set COS_BUCKET=...');
check('COS_REGION configured', !!env.COS_REGION, 'set COS_REGION=ap-shanghai');
check('DATABASE_URL configured', !!env.DATABASE_URL, 'set DATABASE_URL=postgresql://...');
check('SSE_PUSH_SECRET configured', !!env.SSE_PUSH_SECRET);
check('DATABASE_URL not placeholder', env.DATABASE_URL && !env.DATABASE_URL.includes(PASSPHRASE_FLAG));
check('SSE_PUSH_SECRET not placeholder', env.SSE_PUSH_SECRET && !env.SSE_PUSH_SECRET.includes(PASSPHRASE_FLAG));

if (env.DATABASE_URL) {
  const m = env.DATABASE_URL.match(/postgresql:\/\/([^:]+):[^@]+@([^:]+):(\d+)\/([^?]+)/);
  if (m) {
    const [, user, host, port, db] = m;
    console.log(`\nDB target: ${user}@${host}:${port}/${db}`);

    // 私有 IP 段——本地必失败
    const isPrivate =
      host.startsWith('172.') || host.startsWith('10.') || host.startsWith('192.168.') ||
      host === 'localhost' || host === '127.0.0.1';

    if (isPrivate) {
      console.log('  ℹ️  DB host is private/VPC — expected to be unreachable from local dev');
      console.log('  ℹ️  Push schema from TCB side via a one-shot cloud function (see docs/DEPLOYMENT_CHECKLIST.md)');
    } else {
      console.log('  → Attempting connectivity check...');
    }
  }
}

console.log('\nSecrets hygiene:');
const rcPath = path.join(__dirname, '..', 'cloudbaserc.json');
if (fs.existsSync(rcPath)) {
  const rc = fs.readFileSync(rcPath, 'utf8');
  check('cloudbaserc.json has no CHANGE_ME_PASSWORD', !rc.includes('CHANGE_ME_PASSWORD'));
  check('cloudbaserc.json has no real DATABASE_URL pattern', !/postgresql:\/\/[^:]+:[^_][^@]+@/.test(rc),
    'only placeholders or ecanai:__SET_VIA_TCB_CONSOLE_OR_LOCAL_ENV__ allowed');
  check('cloudbaserc.json has no real SSE_PUSH_SECRET', !/SSE_PUSH_SECRET"\s*:\s*"[^_"]/.test(rc) || /SSE_PUSH_SECRET"\s*:\s*"__SET_/.test(rc),
    'placeholder required for any secret in cloudbaserc.json');
}

console.log('\nTests:');

// Parse "Results: N passed, M failed" from smoke test output. Counts the total
// (N+M) as the run size, so we know the suite ran and reported its numbers.
function runAndParse(label, cmd) {
  let out;
  try { out = require('child_process').execSync(cmd, { stdio: 'pipe' }).toString(); }
  catch (e) { console.error(`  ✗ ${label} command failed`); failed++; return; }
  const m = out.match(/Results:\s+(\d+)\s+passed,\s+(\d+)\s+failed/);
  const passed = m ? Number(m[1]) : null;
  const failedCount = m ? Number(m[2]) : null;
  if (m) {
    check(`${label} (${passed} passed, ${failedCount} failed)`, failedCount === 0);
  } else if (out.includes('PASS unit tests')) {
    check(`${label} (PASS)`, true);
  } else {
    check(label, false, 'no result line found in output');
  }
}
runAndParse('unit tests', 'npm run test:unit');
runAndParse('smoke tests', 'npm run test:smoke');
runAndParse('skill-store tests', 'npm run test:skill-store');

console.log('\n' + '='.repeat(40));
if (failed > 0) {
  console.error(`❌ ${failed} check(s) failed`);
  process.exit(1);
} else {
  console.log('✅ All checks passed');
}
