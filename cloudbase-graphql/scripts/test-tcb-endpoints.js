#!/usr/bin/env node
/**
 * 测试脚本：验证 TCB GraphQL API 和 SSE 接口
 * 
 * 用法:
 *   node scripts/test-tcb-endpoints.js
 */

const https = require('https');
const http = require('http');

// 配置
const HOST = 'sccb0-d0gc5398xf028be6a.service.tcloudbase.com';
const GRAPHQL_PATH = '/api/graphql';
const SSE_PATH = '/api/events';

// 简化 HTTP 请求
function httpRequest(url, options = {}) {
  return new Promise((resolve, reject) => {
    const req = https.request(url, options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, body: data }));
    });
    req.on('error', reject);
    req.setTimeout(10000, () => { req.destroy(); reject(new Error('Request timeout')); });
    if (options.body) req.write(options.body);
    req.end();
  });
}

// 测试 GraphQL 端点
async function testGraphQL() {
  console.log('\n========== 测试 GraphQL API ==========\n');
  
  const query = JSON.stringify({
    query: `{ __typename }`
  });
  
  const url = `https://${HOST}${GRAPHQL_PATH}`;
  
  try {
    const result = await httpRequest(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(query)
      },
      body: query
    });
    
    console.log(`GraphQL 端点: ${url}`);
    console.log(`状态码: ${result.status}`);
    console.log(`响应: ${result.body}`);
    
    // 验证：应该返回 UNAUTHENTICATED 错误（需要 token）
    if (result.body.includes('UNAUTHENTICATED') || result.body.includes('Bearer token')) {
      console.log('\n✅ GraphQL API 正常（需要认证是预期行为）');
      return true;
    } else {
      console.log('\n⚠️  GraphQL API 响应异常');
      return false;
    }
  } catch (err) {
    console.error(`\n❌ GraphQL API 测试失败: ${err.message}`);
    return false;
  }
}

// 测试 SSE 端点
async function testSSE() {
  console.log('\n========== 测试 SSE 接口 ==========\n');
  
  const testTopics = ['global', 'health'];
  let allPassed = true;
  
  for (const topic of testTopics) {
    console.log(`\n测试 Topic: ${topic}`);
    
    const url = `https://${HOST}${SSE_PATH}?topic=${topic}`;
    console.log(`SSE 端点: ${url}`);
    
    try {
      // SSE 使用 http (不是 https)
      const result = await new Promise((resolve, reject) => {
        const req = https.request(url, {
          method: 'GET',
          headers: {
            'Accept': 'text/event-stream',
            'Cache-Control': 'no-cache'
          }
        }, (res) => {
          let data = '';
          let resolved = false;
          
          res.on('data', chunk => {
            data += chunk.toString();
            // 收到任何数据就认为连接成功
            if (!resolved && data.length > 0) {
              resolved = true;
              resolve({ status: res.statusCode, headers: res.headers, body: data.substring(0, 500) });
            }
          });
          
          res.on('end', () => {
            if (!resolved) {
              resolve({ status: res.statusCode, headers: res.headers, body: data || '(empty)' });
            }
          });
        });
        
        req.on('error', reject);
        req.setTimeout(5000, () => { req.destroy(); reject(new Error('SSE timeout')); });
        req.end();
      });
      
      console.log(`状态码: ${result.status}`);
      console.log(`Headers: Content-Type=${result.headers['content-type'] || 'N/A'}`);
      console.log(`响应预览: ${result.body.substring(0, 200)}`);
      
      if (result.status === 200) {
        console.log(`✅ SSE /api/events?topic=${topic} 正常`);
      } else {
        console.log(`⚠️ SSE /api/events?topic=${topic} 返回 ${result.status}`);
        allPassed = false;
      }
    } catch (err) {
      console.error(`❌ SSE 测试失败: ${err.message}`);
      allPassed = false;
    }
  }
  
  return allPassed;
}

// 测试 SSE Health 端点
async function testSSEHealth() {
  console.log('\n========== 测试 SSE Health ==========\n');
  
  const url = `https://${HOST}${SSE_PATH}/healthz`;
  console.log(`Health 端点: ${url}`);
  
  try {
    const result = await httpRequest(url, { method: 'GET' });
    
    console.log(`状态码: ${result.status}`);
    console.log(`响应: ${result.body}`);
    
    if (result.body.includes('ecan-graphql-sse')) {
      console.log('\n✅ SSE Service Health 正常');
      return true;
    } else {
      console.log('\n⚠️  SSE Service Health 响应异常');
      return false;
    }
  } catch (err) {
    console.error(`\n❌ SSE Health 测试失败: ${err.message}`);
    return false;
  }
}

// 主函数
async function main() {
  console.log('╔══════════════════════════════════════════════╗');
  console.log('║   TCB GraphQL API & SSE 接口测试            ║');
  console.log('╚══════════════════════════════════════════════╝');
  
  const graphqlOk = await testGraphQL();
  const sseHealthOk = await testSSEHealth();
  const sseOk = await testSSE();
  
  console.log('\n========== 测试结果汇总 ==========\n');
  console.log(`GraphQL API: ${graphqlOk ? '✅' : '❌'}`);
  console.log(`SSE Health:  ${sseHealthOk ? '✅' : '❌'}`);
  console.log(`SSE Events:  ${sseOk ? '✅' : '❌'}`);
  
  const allPassed = graphqlOk && sseHealthOk && sseOk;
  console.log(`\n${allPassed ? '🎉 所有测试通过！' : '⚠️  部分测试失败，请检查日志'}`);
  
  process.exit(allPassed ? 0 : 1);
}

main().catch(console.error);
