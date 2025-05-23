import { IPC, TextMessage, ConfigMessage, CommandMessage, EventMessage, BaseResponse, BaseMessage } from './types';
import { EventEmitter } from './EventEmitter';

/**
 * IPC 客户端类
 * 用于处理与 Python 后端的 IPC 通信
 */
export class IPCClient extends EventEmitter {
    private static instance: IPCClient;
    private ipc: IPC | null = null;
    private ready = false;

    private constructor() {
        super();
        // 监听 webchannel-ready 事件
        window.addEventListener('webchannel-ready', () => {
            console.log('WebChannel is ready');
            const ipc: IPC = window.ipc;
            this.setIPC(ipc);
            console.log('IPC client initialized successfully');
        });
    }

    /**
     * 获取 IPCClient 实例
     */
    public static getInstance(): IPCClient {
        if (!IPCClient.instance) {
            IPCClient.instance = new IPCClient();
        }
        return IPCClient.instance;
    }

    /**
     * 初始化 IPC 客户端
     */
    public async init(): Promise<void> {
        // 检查是否在 Qt WebEngine 环境中
        if (!window.qt?.webChannelTransport) {
            console.warn('Not running in Qt WebEngine environment');
            return;
        }
        console.log('WebChannel transport available:', window.qt.webChannelTransport);
    }

    /**
     * 获取 IPC 对象
     */
    public getIPC(): IPC | null {
        return this.ipc;
    }

    /**
     * 设置 IPC 对象
     */
    public setIPC(ipc: IPC): void {
        this.ipc = ipc;
        this.ready = true;
        
        // 设置 python_to_web 消息处理
        if (this.ipc.python_to_web) {
            this.ipc.python_to_web.connect((message: string) => {
                try {
                    console.log('Python to Web message:', message);
                    // const parsedMessage = JSON.parse(message) as BaseMessage;
                    // this.emit('message', parsedMessage);
                    
                    // // 根据消息类型触发特定事件
                    // if (parsedMessage.type) {
                    //     this.emit(parsedMessage.type, parsedMessage);
                    // }
                } catch (error) {
                    console.error('Error parsing python_to_web message:', error);
                }
            });
        }
    }

    /**
     * 检查 IPC 是否就绪
     */
    public isReady(): boolean {
        return this.ready && this.ipc !== null;
    }

    /**
     * 等待 IPC 就绪
     */
    public async waitForReady(): Promise<void> {
        if (this.isReady()) {
            return;
        }

        return new Promise((resolve) => {
            const check = () => {
                if (this.isReady()) {
                    resolve();
                } else {
                    console.log('IPC client not ready, retrying...');
                    setTimeout(check, 100);
                }
            };
            check();
        });
    }

    /**
     * 监听 Python 到 Web 的消息
     * @param type 消息类型，可以是 'message' 或具体的消息类型
     * @param callback 回调函数
     */
    public onPythonMessage(type: string, callback: (message: BaseMessage) => void): void {
        this.on(type, callback);
    }

    /**
     * 移除 Python 到 Web 的消息监听
     * @param type 消息类型
     * @param callback 回调函数
     */
    public offPythonMessage(type: string, callback: (message: BaseMessage) => void): void {
        this.off(type, callback);
    }

    /**
     * 发送文本消息
     */
    public async sendTextMessage(content: string): Promise<BaseResponse> {
        await this.waitForReady();

        const message: TextMessage = {
            type: 'message',
            content,
            timestamp: new Date().toISOString()
        };

        try {
            const response = await this.ipc!.web_to_python(JSON.stringify(message));
            return JSON.parse(response);
        } catch (error) {
            return {
                status: 'error',
                message: error instanceof Error ? error.message : 'Unknown error',
                timestamp: new Date().toISOString()
            };
        }
    }

    /**
     * 发送配置消息
     */
    public async sendConfigMessage(action: 'get' | 'set', key: string, value?: string): Promise<BaseResponse> {
        await this.waitForReady();

        const message: ConfigMessage = {
            type: 'config',
            action,
            key,
            value,
            timestamp: new Date().toISOString()
        };

        try {
            const response = await this.ipc!.web_to_python(JSON.stringify(message));
            return JSON.parse(response);
        } catch (error) {
            return {
                status: 'error',
                message: error instanceof Error ? error.message : 'Unknown error',
                timestamp: new Date().toISOString()
            };
        }
    }

    /**
     * 发送命令消息
     */
    public async sendCommandMessage(command: string, args?: unknown[]): Promise<BaseResponse> {
        await this.waitForReady();

        const message: CommandMessage = {
            type: 'command',
            command,
            args: args ? { args } : undefined,
            timestamp: new Date().toISOString()
        };

        try {
            const response = await this.ipc!.web_to_python(JSON.stringify(message));
            return JSON.parse(response);
        } catch (error) {
            return {
                status: 'error',
                message: error instanceof Error ? error.message : 'Unknown error',
                timestamp: new Date().toISOString()
            };
        }
    }

    /**
     * 发送事件消息
     */
    public async sendEventMessage(event: string, data?: unknown): Promise<BaseResponse> {
        await this.waitForReady();

        const message: EventMessage = {
            type: 'event',
            event,
            data: data ? { data } : undefined,
            timestamp: new Date().toISOString()
        };

        try {
            const response = await this.ipc!.web_to_python(JSON.stringify(message));
            return JSON.parse(response);
        } catch (error) {
            return {
                status: 'error',
                message: error instanceof Error ? error.message : 'Unknown error',
                timestamp: new Date().toISOString()
            };
        }
    }
}

// 导出单例实例
export const ipcClient = IPCClient.getInstance(); 