import { IPCService } from './ipcService';
import { useIPC } from './useIPC';
import type {
    IPC,
    BaseMessage,
    BaseResponse,
    TextMessage,
    ConfigMessage,
    CommandMessage,
    EventMessage,
    ConfigData,
    CommandData,
    EventData
} from './types';

// 导出类型
export type {
    IPC,
    BaseMessage,
    BaseResponse,
    TextMessage,
    ConfigMessage,
    CommandMessage,
    EventMessage,
    ConfigData,
    CommandData,
    EventData
};

// 导出服务
export { IPCService, useIPC };

// 初始化 IPC 服务
const ipcService = IPCService.getInstance();

// 导出默认实例
export default ipcService; 