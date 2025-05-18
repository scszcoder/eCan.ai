import type { IPCRequest, IPCResponse, IPCMethods, ProcessResult, TaskStatus, SystemInfo, AppSettings } from '../types/ipc';

class IPCClient implements IPCMethods {
    private socket!: WebSocket;
    private messageQueue: Map<string, (value: unknown) => void>;
    private reconnectAttempts: number = 0;
    private maxReconnectAttempts: number = 5;
    private connectionPromise: Promise<void> | null = null;

    constructor() {
        this.messageQueue = new Map();
        this.connect();
    }

    private connect() {
        this.connectionPromise = new Promise((resolve, reject) => {
            this.socket = new WebSocket('ws://localhost:6000');
            
            this.socket.onopen = () => {
                this.reconnectAttempts = 0;
                resolve();
            };

            this.socket.onerror = (error) => {
                reject(error);
            };
            
            this.socket.onmessage = (event) => {
                const response: IPCResponse = JSON.parse(event.data);
                const callback = this.messageQueue.get(response.id);
                if (callback) {
                    callback(response.result);
                    this.messageQueue.delete(response.id);
                }
            };

            this.socket.onclose = () => {
                this.handleReconnect();
            };
        });
    }

    private handleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            setTimeout(() => this.connect(), 1000 * this.reconnectAttempts);
        }
    }

    private async waitForConnection() {
        if (!this.connectionPromise) {
            this.connect();
        }
        try {
            await this.connectionPromise;
        } catch (error) {
            console.error('WebSocket connection failed:', error);
            throw new Error('Failed to connect to WebSocket server');
        }
    }

    private async call<T>(method: string, ...args: unknown[]): Promise<T> {
        await this.waitForConnection();
        
        const id = Math.random().toString(36).substr(2, 9);
        return new Promise<T>((resolve, reject) => {
            const timeout = setTimeout(() => {
                this.messageQueue.delete(id);
                reject(new Error('Request timeout'));
            }, 5000);

            this.messageQueue.set(id, (value: unknown) => {
                clearTimeout(timeout);
                resolve(value as T);
            });

            try {
                const request: IPCRequest = { id, method, args };
                this.socket.send(JSON.stringify(request));
            } catch (error) {
                clearTimeout(timeout);
                this.messageQueue.delete(id);
                reject(error);
            }
        });
    }

    // 实现 IPCMethods 接口
    async getData(key: string): Promise<unknown> {
        return this.call<unknown>('getData', key);
    }

    async setData(key: string, value: unknown): Promise<boolean> {
        return this.call<boolean>('setData', key, value);
    }

    async processData(data: unknown): Promise<ProcessResult> {
        return this.call<ProcessResult>('processData', data);
    }

    async startTask(taskId: string): Promise<TaskStatus> {
        return this.call<TaskStatus>('startTask', taskId);
    }

    async stopTask(taskId: string): Promise<TaskStatus> {
        return this.call<TaskStatus>('stopTask', taskId);
    }

    async getSystemInfo(): Promise<SystemInfo> {
        return this.call<SystemInfo>('getSystemInfo');
    }

    async updateSettings(settings: AppSettings): Promise<boolean> {
        return this.call<boolean>('updateSettings', settings);
    }
}

export const ipcClient = new IPCClient(); 