#!/usr/bin/env node
'use strict';

const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const WebSocket = require('ws');

const API_SCF = process.env.TCB_TEST_API_SCF || 'ecan-graphql-api-test';
const WS_URL = process.env.TCB_TEST_WS_URL;
const ENV_ID = process.env.TCB_ENV_ID || 'sccb0-d0gc5398xf028be6a';
const TEST_SECRET = process.env.WS_TEST_AUTH_SECRET || '';
const TEST_OWNER = process.env.TCB_TEST_OWNER || 'ws-cloud-smoke';
const CLI = process.env.CLOUDBASE_CLI || '/tmp/cloudbase-cli-3.7.3/node_modules/@cloudbase/cli/dist/standalone/cli.js';
const RUN_ID = `ws-cloud-${Date.now()}-${crypto.randomBytes(3).toString('hex')}`;

function requireConfiguration() {
  if (!WS_URL) throw new Error('TCB_TEST_WS_URL is required');
  if (TEST_SECRET.length < 32) throw new Error('WS_TEST_AUTH_SECRET must be at least 32 characters');
}

function createTestToken() {
  const payload = Buffer.from(JSON.stringify({
    aud: 'ecan-graphql-ws-test', sub: TEST_OWNER, exp: Math.floor(Date.now() / 1000) + 120,
  })).toString('base64url');
  const signature = crypto.createHmac('sha256', TEST_SECRET)
    .update(`ecan-ws-test-v1.${payload}`).digest('base64url');
  return `ecan-ws-test-v1.${payload}.${signature}`;
}

function waitForFrame(frames, predicate, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const timer = setInterval(() => {
      const frame = frames.find(predicate);
      if (frame) { clearInterval(timer); resolve(frame); }
    }, 25);
    setTimeout(() => { clearInterval(timer); reject(new Error('WebSocket frame timeout')); }, timeoutMs);
  });
}

function invokePublish() {
  const event = {
    action: 'direct_graphql_test', owner: TEST_OWNER,
    query: 'mutation Publish($input: TaskStatusInput!) { publishTaskStatus(input: $input) { runID success runner status } }',
    variables: { input: { runID: RUN_ID, success: true, runner: 'cloud-ws-e2e', status: { phase: 'complete' } } },
  };
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'ecan-ws-e2e-'));
  const eventFile = path.join(directory, 'event.json');
  fs.writeFileSync(eventFile, JSON.stringify(event), { mode: 0o600 });
  try {
    const result = spawnSync(process.execPath, [CLI, 'fn', 'invoke', API_SCF, '-e', ENV_ID, '-d', `@${eventFile}`, '--json'], { encoding: 'utf8' });
    if (result.status !== 0) throw new Error(`SCF publish invocation failed: ${(result.stderr || result.stdout).trim()}`);
    const output = JSON.parse(result.stdout);
    const envelope = output.data || output;
    const response = envelope.RetMsg || envelope.InvokeResult || output.result || output.Result || envelope;
    const parsedResponse = typeof response === 'string' ? JSON.parse(response) : response;
    const body = typeof parsedResponse.body === 'string' ? JSON.parse(parsedResponse.body) : parsedResponse.body || parsedResponse;
    if (body.errors) throw new Error(`GraphQL publish failed: ${JSON.stringify(body.errors)}`);
    if (body.data?.publishTaskStatus?.runID !== RUN_ID) throw new Error('GraphQL publish returned an unexpected runID');
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
}

async function main() {
  requireConfiguration();
  const header = Buffer.from(JSON.stringify({ Authorization: `Bearer ${createTestToken()}` })).toString('base64');
  const separator = WS_URL.includes('?') ? '&' : '?';
  const socket = new WebSocket(`${WS_URL}${separator}header=${encodeURIComponent(header)}&payload=e30=`, 'graphql-ws');
  const frames = [];
  socket.on('message', raw => frames.push(JSON.parse(raw.toString())));
  try {
    await new Promise((resolve, reject) => { socket.once('open', resolve); socket.once('error', reject); });
    socket.send(JSON.stringify({ type: 'connection_init' }));
    await waitForFrame(frames, frame => frame.type === 'connection_ack');
    socket.send(JSON.stringify({ id: RUN_ID, type: 'start', payload: { data: JSON.stringify({
      query: 'subscription Status($runID: ID!) { onTaskStatus(runID: $runID) { runID success runner status } }', variables: { runID: RUN_ID },
    }) } }));
    await waitForFrame(frames, frame => frame.type === 'start_ack' && frame.id === RUN_ID);
    invokePublish();
    const frame = await waitForFrame(frames, candidate => candidate.type === 'data' && candidate.id === RUN_ID && candidate.payload?.data?.onTaskStatus?.runID === RUN_ID);
    if (frame.payload.data.onTaskStatus.success !== true) throw new Error('Delivered event was not successful');
    socket.send(JSON.stringify({ type: 'stop', id: RUN_ID }));
    console.log(`PASS WebSocket publish/subscribe run ${RUN_ID}`);
  } finally {
    socket.close();
  }
}

main().catch(error => { console.error(`FAIL ${error.message}`); process.exitCode = 1; });