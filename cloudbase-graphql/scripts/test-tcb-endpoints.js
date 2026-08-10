#!/usr/bin/env node
/**
 * 测试脚本：验证 TCB GraphQL API 和 WS 服务接口
 *
 * 用法: node scripts/test-tcb-endpoints.js
 */

const https = require('https');
const http = require('http');
const { WebSocket } = require('ws');

const HOST = process.env.TCB_HOST || 'sccb0-d0gc5398xf028be6a.service.tcloudbase.com';
const GRAPHQL_PATH = '/api/graphql';
const WS_PATH = '/ws';
const PUSH_PATH = '/publish';

function httpRequest(url, options = {}) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const lib = u.protocol === 'https:' ? https : http;
    const req = lib.request({
      hostname: u.hostname, port: u.port || (u.protocol === 'https:' ? 443 : 80),
      path: u.pathname + u.search,
      method: options.method || 'GET',
      headers: options.headers || {},
    }, (res) => {
      let body = '';
      res.on('data', c => body += c);
      res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, body }));
    });
    req.on('error', reject);
    req.setTimeout(10000, () => { req.destroy(); reject(new Error('timeout')); });
    if (options.body) req.write(options.body);
    req.end();
  });
}

// 测试 GraphQL 端点
async function testGraphQL() {
  console.log('\n========== 测试 GraphQL API ==========\n');
  const query = JSON.stringify({ query: '{ __typename }' });
  try {
    const r = await httpRequest(`https://${HOST}${GRAPHQL_PATH}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(query) },
      body: query,
    });
    if (r.status === 200) {
      console.log(`✅ GraphQL /api/graphql 正常 (${r.body.length} bytes)`);
      return true;
    }
    console.log(`⚠️ GraphQL 返回 ${r.status}`);
    return false;
  } catch (err) {
    console.error(`❌ GraphQL 测试失败: ${err.message}`);
    return false;
  }
}

// 测试 WS Health 端点
async function testWSHealth() {
  console.log('\n========== 测试 WS /healthz ==========\n');
  const url = `http://${HOST}/healthz`;
  try {
    const r = await httpRequest(url);
    if (r.status === 200 && r.body.includes('"status":"ok"')) {
      console.log(`✅ WS /healthz 正常: ${r.body.substring(0, 100)}`);
      return true;
    }
    console.log(`⚠️ WS /healthz 返回 ${r.status}: ${r.body}`);
    return false;
  } catch (err) {
    console.error(`❌ WS /healthz 测试失败: ${err.message}`);
    return false;
  }
}

// 测试 WS WebSocket 连接
async function testWSConnection() {
  console.log('\n========== 测试 WS WebSocket 连接 ==========\n');
  const token = process.env.TEST_TOKEN || 'test-jwt';
  const headerB64 = Buffer.from(JSON.stringify({ Authorization: `Bearer ${token}` })).toString('base64');
  const wsUrl = `ws://${HOST}${WS_PATH}/?header=${headerB64}`;

  return new Promise((resolve) => {
    console.log(`WS URL: ${wsUrl}`);
    const ws = new WebSocket(wsUrl, 'graphql-ws');
    let passed = false;
    const done = (result, msg) => {
      if (!passed) {
        passed = true;
        console.log(`${result ? '✅' : '❌'} ${msg}`);
      }
      ws.close();
      resolve(result);
    };

    ws.on('open', () => {
      console.log('  → 连接已打开');
      // 发送 connection_init
      ws.send(JSON.stringify({ type: 'connection_init' }));
    });

    ws.on('message', (data) => {
      const frame = JSON.parse(data.toString());
      console.log(`  ← 收到帧: ${frame.type}`);
      if (frame.type === 'connection_ack') {
        done(true, 'connection_init → connection_ack');
        // 发送 connection_terminate
        ws.send(JSON.stringify({ type: 'connection_terminate' }));
      }
    });

    ws.on('error', (err) => {
      done(false, `WS 连接错误: ${err.message}`);
    });

    ws.on('close', () => {
      done(false, 'WS 连接在收到 ack 前关闭');
    });

    setTimeout(() => done(false, 'WS 连接超时'), 10000);
  });
}

async function main() {
  console.log('╔══════════════════════════════════════════════╗');
  console.log('║   TCB GraphQL API & WS 接口测试            ║');
  console.log('╚══════════════════════════════════════════════╝');
  console.log(`\n目标主机: ${HOST}`);

  const graphqlOk = await testGraphQL();
  const wsHealthOk = await testWSHealth();
  const wsOk = await testWSConnection();

  console.log('\n========== 测试结果汇总 ==========\n');
  console.log(`GraphQL API: ${graphqlOk ? '✅' : '❌'}`);
  console.log(`WS /healthz: ${wsHealthOk ? '✅' : '❌'}`);
  console.log(`WS WebSocket: ${wsOk ? '✅' : '❌'}`);

  const allPassed = graphqlOk && wsHealthOk && wsOk;
  console.log(`\n${allPassed ? '🎉 所有测试通过！' : '⚠️  部分测试失败，请检查日志'}`);

  process.exit(allPassed ? 0 : 1);
}

main().catch((err) => {
  console.error('Fatal:', err);
  process.exit(1);
});
