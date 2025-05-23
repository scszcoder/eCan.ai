import { IPC, TextMessage, ConfigMessage, CommandMessage, EventMessage, BaseResponse } from './types';

/**
 * IPC 服务类
 * 用于处理与 Python 后端的通信
 */
export class IPCService {
    private static instance: IPCService;
    private ipc: IPC | null = null;
    private ready = false;

    private constructor() {}

    /**
     * 获取 IPCService 实例
     */
    public static getInstance(): IPCService {
        if (!IPCService.instance) {
            IPCService.instance = new IPCService();
        }
        return IPCService.instance;
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
                    console.log('IPC not ready');
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
        if (!this.isReady()) {
            throw new Error('IPC not ready');
        }

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
        if (!this.isReady()) {
            throw new Error('IPC not ready');
        }

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
        if (!this.isReady()) {
            throw new Error('IPC not ready');
        }

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
        if (!this.isReady()) {
            throw new Error('IPC not ready');
        }

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