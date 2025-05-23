import { IPC } from './types';

/**
 * IPC 服务类
 * 用于处理与 Python 后端的通信
 */
export class IPCService {
    private static instance: IPCService;
    private ipc: IPC | null = null;
    private ready = false;
    private pendingCallbacks: Array<() => void> = [];

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
     * 初始化 IPC 服务
     * @param ipc IPC 对象
     */
    public init(ipc: IPC): void {
        this.ipc = ipc;
        this.ready = true;
        this.executePendingCallbacks();
    }

    /**
     * 执行等待中的回调函数
     */
    private executePendingCallbacks(): void {
        while (this.pendingCallbacks.length > 0) {
            const callback = this.pendingCallbacks.shift();
            if (callback) {
                callback();
            }
        }
    }

    /**
     * 等待 IPC 就绪
     * @returns Promise<void>
     */
    public async waitForReady(): Promise<void> {
        if (this.ready) {
            return;
        }

        return new Promise((resolve) => {
            this.pendingCallbacks.push(resolve);
        });
    }

    /**
     * 获取 IPC 对象
     * @returns IPC 对象
     */
    public getIPC(): IPC {
        if (!this.ipc) {
            throw new Error('IPC not initialized');
        }
        return this.ipc;
    }
} 