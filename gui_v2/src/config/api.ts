/**
 * API 客户端配置 —— 共享枚举。
 *
 * 设计原则：
 * 1. 前端只需要知道后端地址
 * 2. 不关心是 AWS 还是腾讯云，不关心 Cognito 还是 TCB
 * 3. 不同 product 的差异由后端配置决定，前端统一构建
 * 4. 云端后端是透明的，前端只对接 GraphQL 接口
 *
 * 端点地址：统一通过 useAppConfig() 拿运行时配置；
 * runtime 真值源是后端 IPC handler getAppConfig（见
 * gui_v2/src/contexts/AppConfigContext.tsx）。
 */

export enum Channel {
  LOCAL = 'local',
  CLOUD = 'cloud',
}