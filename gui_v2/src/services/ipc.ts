import { logger } from '../utils/logger';

// 定义 WebChannel 桥接器类型
interface WebChannelBridge {
  sendToPython: (message: string) => void;
  dataReceived: {
    connect: (callback: (message: string) => void) => void;
  };
}

// 扩展 Window 接口
declare global {
  interface Window {
    bridge?: WebChannelBridge;
  }
}

// 定义日志类型
interface LogEntry {
  level: string;
  message: string;
  timestamp: string;
  source?: string;
  line?: number;
}

// 定义网络请求类型
interface NetworkRequest {
  url: string;
  method: string;
  status: number;
  timestamp: string;
  headers: Record<string, string>;
  body?: string;
}

// 定义元素日志类型
interface ElementLog {
  type: string;
  selector: string;
  timestamp: string;
  details: Record<string, unknown>;
}

// IPC 消息类型定义
export interface IPCMessage {
  type: 'command' | 'request' | 'response';
  command?: string;
  requestType?: string;
  responseType?: string;
  data?: Record<string, unknown>;
  result?: unknown;
  error?: string;
}

export interface IPCResponse {
  type: 'response';
  responseType: string;
  result?: unknown;
  error?: string;
}

// IPC 服务类
class IPCService {
  private static instance: IPCService;
  private bridge?: WebChannelBridge;
  private eventHandlers: Map<string, Set<(data: unknown) => void>>;
  private responseHandlers: Map<string, Set<(data: IPCResponse) => void>>;

  private constructor() {
    this.eventHandlers = new Map();
    this.responseHandlers = new Map();
    this.initializeWebChannel();
  }

  public static getInstance(): IPCService {
    if (!IPCService.instance) {
      IPCService.instance = new IPCService();
    }
    return IPCService.instance;
  }

  private initializeWebChannel() {
    // 等待 WebChannel 初始化
    const checkBridge = () => {
      if (window.bridge) {
        this.bridge = window.bridge;
        this.setupMessageHandling();
        logger.info('WebChannel initialized successfully');
      } else {
        setTimeout(checkBridge, 100);
      }
    };
    checkBridge();
  }

  private setupMessageHandling() {
    if (!this.bridge) return;

    // 监听来自 Python 的消息
    this.bridge.dataReceived.connect((message: string) => {
      try {
        const data = JSON.parse(message) as IPCMessage;
        logger.debug('Received from Python:', data);

        if (data.type === 'response') {
          this.handleResponse(data as IPCResponse);
        }
      } catch (e) {
        logger.error('Error parsing message from Python:', e);
      }
    });
  }

  private handleResponse(response: IPCResponse) {
    const handlers = this.responseHandlers.get(response.responseType);
    if (handlers) {
      handlers.forEach(handler => handler(response));
    }
  }

  // 发送命令到 Python
  public sendCommand(command: string, data?: Record<string, unknown>): void {
    const message: IPCMessage = {
      type: 'command',
      command,
      data
    };
    this.sendToPython(message);
  }

  // 发送请求到 Python
  public async sendRequest<T>(requestType: string, data?: Record<string, unknown>): Promise<T> {
    return new Promise((resolve, reject) => {
      const message: IPCMessage = {
        type: 'request',
        requestType,
        data
      };

      // 注册一次性响应处理器
      const handler = (response: IPCResponse) => {
        if (response.error) {
          reject(new Error(response.error));
        } else {
          resolve(response.result as T);
        }
        this.unregisterResponseHandler(requestType, handler);
      };

      this.registerResponseHandler(requestType, handler);
      this.sendToPython(message);
    });
  }

  // 发送消息到 Python
  private sendToPython(message: IPCMessage): void {
    if (!this.bridge) {
      logger.error('WebChannel not initialized');
      return;
    }

    try {
      const messageStr = JSON.stringify(message);
      this.bridge.sendToPython(messageStr);
      logger.debug('Sent to Python:', message);
    } catch (e) {
      logger.error('Error sending message to Python:', e);
    }
  }

  // 注册事件处理器
  public registerEventHandler(eventType: string, handler: (data: unknown) => void): void {
    if (!this.eventHandlers.has(eventType)) {
      this.eventHandlers.set(eventType, new Set());
    }
    this.eventHandlers.get(eventType)!.add(handler);
  }

  // 注销事件处理器
  public unregisterEventHandler(eventType: string, handler: (data: unknown) => void): void {
    const handlers = this.eventHandlers.get(eventType);
    if (handlers) {
      handlers.delete(handler);
    }
  }

  // 注册响应处理器
  public registerResponseHandler(responseType: string, handler: (data: IPCResponse) => void): void {
    if (!this.responseHandlers.has(responseType)) {
      this.responseHandlers.set(responseType, new Set());
    }
    this.responseHandlers.get(responseType)!.add(handler);
  }

  // 注销响应处理器
  public unregisterResponseHandler(responseType: string, handler: (data: IPCResponse) => void): void {
    const handlers = this.responseHandlers.get(responseType);
    if (handlers) {
      handlers.delete(handler);
    }
  }

  // 预定义的命令方法
  public reload(): void {
    this.sendCommand('reload');
  }

  public toggleDevTools(): void {
    this.sendCommand('toggle_dev_tools');
  }

  public clearLogs(): void {
    this.sendCommand('clear_logs');
  }

  public executeScript(script: string): void {
    this.sendCommand('execute_script', { script });
  }

  // 预定义的请求方法
  public async getPageInfo(): Promise<{ title: string; url: string; timestamp: string }> {
    return this.sendRequest('get_page_info');
  }

  public async getConsoleLogs(): Promise<LogEntry[]> {
    return this.sendRequest('get_console_logs');
  }

  public async getNetworkLogs(): Promise<NetworkRequest[]> {
    return this.sendRequest('get_network_logs');
  }

  public async getElementLogs(): Promise<ElementLog[]> {
    return this.sendRequest('get_element_logs');
  }
}

// 导出单例实例
export const ipcService = IPCService.getInstance();

// 导出类型
export type { IPCService, LogEntry, NetworkRequest, ElementLog }; 