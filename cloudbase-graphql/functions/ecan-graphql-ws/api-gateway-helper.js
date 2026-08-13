/**
 * api-gateway-helper.js — TCB WebSocket API 网关集成辅助函数
 *
 * 注意: 当前 WS 服务部署在 TCS (云托管) 中，不再使用 TCB SCF WebSocket Trigger。
 * 此文件保留用于调试/测试场景，当需要通过 TCB API 网关代理 WebSocket 时使用。
 *
 * 主要用途:
 *   - 将事件推送到通过 API 网关 WS Trigger 建立的连接
 *   - 仅在 SCF 模式(未使用)时需要
 */

'use strict';

/**
 * 通过 TCB WebSocket API 网关向后端连接推送消息
 *
 * @param {string} apiId       - API 网关 API ID
 * @param {string} connectionId- WebSocket 连接 ID
 * @param {string} data        - 要发送的数据 (JSON 字符串)
 * @param {object} options     - { secretId, secretKey, token }
 * @returns {Promise<boolean>}  - 成功返回 true
 */
async function postToConnection(apiId, connectionId, data, options = {}) {
  const { secretId, secretKey, token } = options;
  if (!secretId || !secretKey) {
    throw new Error('TCB credentials (secretId, secretKey) required');
  }

  const CloudBase = require('@cloudbase/node-sdk');
  const tcb = CloudBase.init({
    secretId,
    secretKey,
    token,
    envId: process.env.TCB_ENV_ID,
  });

  const fc = tcb.getFC();
  const region = process.env.TCB_REGION || 'ap-shanghai';

  const params = {
    ApiId: apiId,
    ConnectionId: connectionId,
    Data: data,
  };

  try {
    await fc.call('SendMessages', params, { region });
    return true;
  } catch (err) {
    console.error('[api-gateway-helper] postToConnection failed:', err.message);
    throw err;
  }
}

module.exports = { postToConnection };
