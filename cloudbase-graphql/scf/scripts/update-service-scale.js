#!/usr/bin/env node
/**
 * update-service-scale.js - 更新 TCB 云托管服务扩缩容配置
 *
 * 用法:
 *   node update-service-scale.js --service ecan-graphql-ws --min 1 --max 5
 *
 * 说明:
 *   使用 TCB CLI 的临时凭证调用腾讯云 CBR API 更新服务的扩缩容配置
 */

const { execSync } = require('child_process');
const https = require('https');

const SERVICE_NAME = process.argv.includes('--service')
  ? process.argv[process.argv.indexOf('--service') + 1]
  : 'ecan-graphql-ws';

const MIN_NUM = process.argv.includes('--min')
  ? parseInt(process.argv[process.argv.indexOf('--min') + 1], 10)
  : 1;

const MAX_NUM = process.argv.includes('--max')
  ? parseInt(process.argv[process.argv.indexOf('--max') + 1], 10)
  : 5;

const ENV_ID = 'sccb0-d0gc5398xf028be6a';
const REGION = process.env.TCB_REGION || 'ap-shanghai';

/**
 * 获取 TCB CLI 临时凭证
 */
function getCredentials() {
  console.log('正在获取 TCB 临时凭证...');
  const output = execSync('tcb secrets get --json', { encoding: 'utf-8' });
  const creds = JSON.parse(output);
  return creds.data;
}

/**
 * 获取腾讯云 CAM Token (用于 CBR API)
 */
function getCamToken() {
  console.log('正在获取 CAM Token...');
  const output = execSync('tcb token get --json', { encoding: 'utf-8' });
  const result = JSON.parse(output);
  return result.data;
}

/**
 * 直接调用腾讯云 CBR API 更新扩缩容配置
 */
async function updateViaCBRApi(camToken) {
  console.log(`正在通过 CBR API 更新扩缩容配置: MinNum=${MIN_NUM}, MaxNum=${MAX_NUM}...`);

  return new Promise((resolve) => {
    const endpoint = 'cbr.api.qcloud.com';
    const action = 'ModifyCloudBaseRunServiceScale';

    const payload = {
      EnvId: ENV_ID,
      ServerName: SERVICE_NAME,
      MinNum: MIN_NUM,
      MaxNum: MAX_NUM
    };

    const body = JSON.stringify(payload);
    const bodyLen = Buffer.byteLength(body, 'utf8');

    const options = {
      hostname: endpoint,
      port: 443,
      path: '/v2/index.php',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': bodyLen,
        'Host': endpoint,
        'X-TC-Action': action,
        'X-TC-Region': REGION,
        'X-TC-Token': camToken,
        'X-TC-Version': '2019-07-22'
      }
    };

    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', (chunk) => data += chunk);
      res.on('end', () => {
        try {
          const result = JSON.parse(data);
          if (result.Response && result.Response.Error) {
            console.error(`❌ API 错误: ${result.Response.Error.Message}`);
            resolve(false);
          } else {
            console.log('✓ 扩缩容配置更新成功');
            resolve(true);
          }
        } catch (e) {
          console.error('❌ 解析响应失败:', data);
          resolve(false);
        }
      });
    });

    req.on('error', (e) => {
      console.error(`❌ 请求失败: ${e.message}`);
      resolve(false);
    });

    req.write(body);
    req.end();
  });
}

/**
 * 获取当前服务配置
 */
async function getServiceInfo() {
  console.log(`正在获取服务 ${SERVICE_NAME} 的当前配置...`);
  const output = execSync(
    `tcb cloudrun detail --service-name ${SERVICE_NAME} --env-id ${ENV_ID} --json`,
    { encoding: 'utf-8' }
  );
  return JSON.parse(output);
}

/**
 * 主函数
 */
async function main() {
  try {
    console.log('=== TCB 云托管服务扩缩容配置更新工具 ===');
    console.log('');

    // 获取凭证
    const creds = await getCredentials();
    console.log(`✓ 已获取凭证 (SecretId: ${creds.secretId.substring(0, 10)}...)`);

    // 获取 CAM Token
    const camToken = getCamToken();
    console.log('✓ 已获取 CAM Token');

    // 获取当前配置
    const serviceInfo = await getServiceInfo();
    const currentMin = serviceInfo?.ServerConfig?.MinNum || '未知';
    const currentMax = serviceInfo?.ServerConfig?.MaxNum || '未知';
    console.log(`✓ 当前配置: MinNum=${currentMin}, MaxNum=${currentMax}`);

    if (currentMin === MIN_NUM && currentMax === MAX_NUM) {
      console.log('✓ 配置已是目标值，无需更新');
      return;
    }

    // 更新配置
    const updated = await updateViaCBRApi(camToken);

    if (updated) {
      console.log('✓ 配置更新成功');
    } else {
      console.log('⚠️  请手动完成配置更新');
      process.exit(1);
    }
  } catch (error) {
    console.error('❌ 错误:', error.message);
    process.exit(1);
  }
}

main();
