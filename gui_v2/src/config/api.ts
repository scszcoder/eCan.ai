/**
 * API 客户端配置
 *
 * 设计原则：
 * 1. 前端只需要知道后端地址
 * 2. 不关心是 AWS 还是腾讯云，不关心 Cognito 还是 TCB
 * 3. 不同 product 的差异由后端配置决定，前端统一构建
 * 4. 云端后端是透明的，前端只对接 GraphQL 接口
 *
 * 配置优先级：
 * 1. 后端 /api/config 返回的配置（运行时）
 * 2. 环境变量 VITE_*（构建时，作为后备）
 */

import { useAppConfig, useEndpoints } from '../contexts/AppConfigContext';

export enum Channel {
  LOCAL = 'local',
  CLOUD = 'cloud',
}

/**
 * API 端点配置
 *
 * 优先使用后端配置，其次使用环境变量
 */
export function getAPIEndpoints() {
  // 尝试从后端配置获取
  try {
    const { config } = useAppConfig();
    const { apiBase, wsUrl } = useEndpoints();
    if (config) {
      return {
        apiBase,
        wsUrl,
        appId: config.app_id,
      };
    }
  } catch {
    // Context 不可用，使用环境变量
  }

  // 回退到环境变量
  return {
    apiBase: import.meta.env.VITE_API_BASE || '',
    wsUrl: import.meta.env.VITE_WS_URL || '',
    appId: 'intl',
  };
}

// 静态导出（兼容现有代码）
export const API_BASE_URL = import.meta.env.VITE_API_BASE || '';
export const WS_URL = import.meta.env.VITE_WS_URL || '';
export const APP_ID = import.meta.env.VITE_APP_ID || 'intl';

/**
 * 当前是否云端部署
 */
export const isCloudChannel = (): boolean => {
  if (typeof window === 'undefined') return false;
  const protocol = window.location.protocol;
  if (protocol === 'file:') return false;
  const hostname = window.location.hostname;
  if (hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1') return false;
  if (hostname.startsWith('10.') || hostname.startsWith('192.168.')) return false;
  return true;
};

/**
 * 通道选择
 */
export const getChannel = (): Channel =>
  isCloudChannel() ? Channel.CLOUD : Channel.LOCAL;
