import { IPC, TextMessage, ConfigMessage, CommandMessage, EventMessage, BaseResponse } from './types';

/**
 * IPC 客户端类
 * 用于处理与 Python 后端的 IPC 通信
 */
export class IPCClient {
    private static instance: IPCClient;
    private ipc: IPC | null = null;
    private ready = false;

    private constructor() {
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