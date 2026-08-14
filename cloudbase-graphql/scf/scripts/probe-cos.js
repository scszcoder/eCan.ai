#!/usr/bin/env node
/**
 * Quick COS connectivity probe for the CN app.
 *
 * Loads credentials from cloudbase-graphql/.env.local (gitignored, local dev).
 * Then runs a sequence of probes against the runtime bucket (ecan-skills-1251680599, ap-shanghai):
 *
 *   1. List the bucket root  → does it respond at all?
 *   2. Upload a small test object under e2e_probe/{uuid}.txt
 *   3. GET a signed URL for it
 *   4. GET the signed URL with stdlib https
 *   5. Delete the object
 *   6. Confirm deletion with headObject
 *
 * Usage (from repo root):
 *
 *   node cloudbase-graphql/scripts/probe-cos.js
 *
 * Prerequisites:
 *   - cloudbase-graphql/.env.local must exist and contain COS_BUCKET / COS_REGION
 *   - Node.js >= 16
 *   - npm install (cos-nodejs-sdk-v5 is already a dependency)
 *
 * If credentials are missing / wrong, the script exits with a non-zero code
 * and prints which step failed.
 */
'use strict';

const path = require('path');
const https = require('https');
const http = require('http');
const { readFileSync } = require('fs');
const crypto = require('crypto');

// ── dotenv (bundled with node, no install needed in Node 20.6+; graceful no-op) ──
try {
  // Node.js 20.6+ auto-loads .env files; try it first
  if (!process.env.COS_BUCKET) {
    const envPath = path.resolve(__dirname, '../.env.local');
    const content = readFileSync(envPath, 'utf8');
    for (const line of content.split('\n')) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const eq = trimmed.indexOf('=');
      if (eq < 0) continue;
      const key = trimmed.slice(0, eq).trim();
      const val = trimmed.slice(eq + 1).trim().replace(/^["']|["']$/g, '');
      if (!process.env[key]) process.env[key] = val;
    }
    console.log('  [dotenv] Loaded .env.local');
  }
} catch (err) {
  console.log('  [dotenv] .env.local not found or unreadable:', err.message);
}

const BUCKET = process.env.COS_BUCKET || process.env.TCB_COS_BUCKET;
const REGION = process.env.COS_REGION || process.env.TCB_REGION || 'ap-shanghai';

// ── COS SDK (loaded lazily to keep probe self-contained) ──
let COS;
function getCos() {
  if (!COS) {
    const COSMod = require('cos-nodejs-sdk-v5');
    const options = {};

    // Order: explicit Tencent Cloud env vars > TCB credential env vars
    const secretId = process.env.TENCENTCLOUD_SECRETID
      || process.env.ECAN_TENCENT_SECRET_ID
      || '';
    const secretKey = process.env.TENCENTCLOUD_SECRETKEY
      || process.env.ECAN_TENCENT_SECRET_KEY
      || '';
    const token = process.env.TENCENTCLOUD_SESSIONTOKEN || '';

    if (secretId && secretKey) {
      options.SecretId = secretId;
      options.SecretKey = secretKey;
      if (token) options.SecurityToken = token;
    }
    // else: TCB SDK uses the auto-discovered TCB credential in SCF / via TCB auth

    COS = new COSMod(options);
  }
  return COS;
}

// ── Helpers ────────────────────────────────────────────────────────────────

function delay(ms) {
  return new Promise(r => setTimeout(r, ms));
}

function httpGet(url) {
  return new Promise((resolve, reject) => {
    const mod = url.startsWith('https') ? https : http;
    const req = mod.get(url, { timeout: 15000 }, res => {
      let body = '';
      res.on('data', c => (body += c));
      res.on('end', () => resolve({ status: res.statusCode, body }));
    });
    req.on('timeout', () => { req.destroy(); reject(new Error('TIMEOUT')); });
    req.on('error', reject);
  });
}

function cosCall(method, params) {
  return new Promise((resolve, reject) => {
    const cos = getCos();
    if (typeof cos[method] !== 'function') {
      reject(new Error(`COS has no method: ${method}`));
      return;
    }
    cos[method](params, (err, data) => {
      if (err) reject(err);
      else resolve(data);
    });
  });
}

async function probe(name, fn) {
  process.stdout.write(`  ${name.padEnd(50)} → `);
  try {
    const result = await fn();
    console.log('\x1b[32m✓\x1b[0m', typeof result === 'string' ? result : JSON.stringify(result).slice(0, 120));
    return true;
  } catch (err) {
    // Distinguish SDK errors from network errors
    const msg = err.code || err.name || '';
    const detail = err.message || String(err);
    const hint =
      (!msg && !detail) ? 'unknown error (no message)'
      : (detail.includes('getaddrinfo') || detail.includes('ENOTFOUND')) ? `DNS/network: ${detail}`
      : (detail.includes('403') || detail.includes('AccessDenied')) ? 'CREDENTIALS_MISSING — add SecretId/SecretKey or TCB STS token to environment'
      : (detail.includes('NoSuchBucket')) ? `BUCKET_MISSING — bucket "${BUCKET}" does not exist or is inaccessible`
      : (detail.includes('param is missing') || detail.includes('Required')) ? `SDK_USAGE — missing required param: ${detail}`
      : `${msg ? `[${msg}] ` : ''}${detail}`;
    console.log('\x1b[31m✗\x1b[0m', hint);
    return false;
  }
}

// ── Main ─────────────────────────────────────────────────────────────────

async function main() {
  console.log('\n=== COS Connectivity Probe ===');
  console.log('  Bucket:', BUCKET || '\x1b[33m[NOT SET]\x1b[0m');
  console.log('  Region:', REGION || '\x1b[33m[NOT SET]\x1b[0m');
  console.log('  SDK  : cos-nodejs-sdk-v5');

  const results = [];

  if (!BUCKET) {
    console.log('\n\x1b[31mFATAL:\x1b[0m COS_BUCKET not set in environment or .env.local');
    console.log('  Set it in cloudbase-graphql/.env.local:');
    console.log('    COS_BUCKET=your-bucket-appid');
    console.log('    COS_REGION=ap-shanghai');
    process.exit(1);
  }

  const testKey = `e2e_probe/probe-${crypto.randomUUID()}.txt`;
  const testContent = `COS probe test — ${new Date().toISOString()}`;

  console.log('\n─── Step 1: List bucket ────────────────────────────────');
  results.push(await probe(
    `listObjects (prefix '')`,
    async () => {
      const data = await cosCall('getBucket', {
        Bucket: BUCKET, Region: REGION, MaxKeys: 5,
      });
      return `Contents count: ${(data.Contents || []).length}, Name: ${data.Name || data.Bucket || BUCKET}`;
    }
  ));

  console.log('\n─── Step 2: Put object ────────────────────────────────');
  results.push(await probe(
    `putObject (${testKey})`,
    async () => {
      await cosCall('putObject', {
        Bucket: BUCKET,
        Region: REGION,
        Key: testKey,
        Body: testContent,
        ContentType: 'text/plain;charset=utf-8',
      });
      return `stored at ${testKey}`;
    }
  ));

  console.log('\n─── Step 3: Head object ───────────────────────────────');
  results.push(await probe(
    `headObject (${testKey})`,
    async () => {
      const data = await cosCall('headObject', {
        Bucket: BUCKET, Region: REGION, Key: testKey,
      });
      return `ContentLength: ${data.ContentLength}, ETag: ${data.ETag || '(no etag)'}`;
    }
  ));

  console.log('\n─── Step 4: Get signed URL ────────────────────────────');
  let signedUrl = null;
  results.push(await probe(
    `getObjectUrl (GET, 300s)`,
    async () => {
      const data = await new Promise((resolve, reject) => {
        getCos().getObjectUrl({
          Bucket: BUCKET, Region: REGION,
          Key: testKey,
          Method: 'GET',
          Expires: 300,
        }, (err, url) => {
          if (err) reject(err);
          else resolve(url);
        });
      });
      // SDK v3.0.0 returns { Url: string } — handle both shapes
      signedUrl = (typeof data === 'object' && data !== null && data.Url) ? data.Url : data;
      if (!signedUrl || typeof signedUrl !== 'string') throw new Error(`Unexpected return type: ${JSON.stringify(data)}`);
      return signedUrl.replace(/[\?#].*/, '?...');
    }
  ));

  if (signedUrl) {
    console.log('\n─── Step 5: GET signed URL ───────────────────────────');
    results.push(await probe(
      `urllib GET signed URL`,
      async () => {
        const { status, body } = await httpGet(signedUrl);
        if (status !== 200) throw new Error(`HTTP ${status}`);
        if (body !== testContent) throw new Error(`Content mismatch: expected "${testContent}", got "${body}"`);
        return `HTTP 200, content matches (${body.length} bytes)`;
      }
    ));
  } else {
    console.log('  [skip] signed URL not available');
    results.push(false);
  }

  console.log('\n─── Step 6: Delete object ───────────────────────────');
  results.push(await probe(
    `deleteObject (${testKey})`,
    async () => {
      await cosCall('deleteObject', { Bucket: BUCKET, Region: REGION, Key: testKey });
      return 'deleted';
    }
  ));

  console.log('\n─── Step 7: Verify deletion ─────────────────────────');
  results.push(await probe(
    `headObject (should 404)`,
    async () => {
      let err;
      try {
        await cosCall('headObject', { Bucket: BUCKET, Region: REGION, Key: testKey });
      } catch (e) {
        err = e;
      }
      // 404 → correct, headObject throws CosServiceError
      if (err && (err.statusCode === 404 || err.code === 'NoSuchResource' || err.code === 'NoSuchKey')) {
        return '404 Not Found — deletion confirmed';
      }
      if (!err) throw new Error('Object still exists after delete!');
      throw err;
    }
  ));

  const passed = results.filter(Boolean).length;
  const total = results.length;
  console.log(`\n${'─'.repeat(60)}`);
  console.log(`  Result: ${passed}/${total} steps passed`);
  if (passed === total) {
    console.log('  \x1b[32m✓ COS is fully functional\x1b[0m');
    process.exit(0);
  } else {
    console.log('  \x1b[31m✗ COS connectivity issues detected\x1b[0m');
    process.exit(1);
  }
}

main().catch(err => {
  console.error('\n\x1b[31mFATAL:\x1b[0m', err.message);
  process.exit(1);
});
