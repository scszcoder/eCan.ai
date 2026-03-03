/**
 * IPC Module - 统一ExportAll IPC Related toComponent
 * WebChannel and WebSocket IPC removed - now uses HTTP GraphQL for requests
 * WebSocket only used for receiving push events (handled in localWebSocketClient)
 */
export * from './types';
export { ipcClient, UnifiedIPCClient, type DeploymentMode, type IPCClientConfig } from './ipcClient';
export * from './api';
export * from './handlers';
export * from './registry';