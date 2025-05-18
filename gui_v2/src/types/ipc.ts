export interface IPCRequest {
    id: string;
    method: string;
    args: unknown[];
}

export interface IPCResponse {
    id: string;
    result: unknown;
    error?: string;
}

export interface ProcessResult {
    success: boolean;
    data: unknown;
    message?: string;
}

export interface TaskStatus {
    taskId: string;
    status: 'running' | 'stopped' | 'error';
    progress?: number;
}

export interface SystemInfo {
    version: string;
    platform: string;
    memory: {
        total: number;
        used: number;
    };
}

export interface AppSettings {
    theme: 'light' | 'dark';
    language: string;
    autoStart: boolean;
}

// 定义所有可用的方法接口
export interface IPCMethods {
    // 数据操作
    getData(key: string): Promise<unknown>;
    setData(key: string, value: unknown): Promise<boolean>;
    
    // 业务操作
    processData(data: unknown): Promise<ProcessResult>;
    startTask(taskId: string): Promise<TaskStatus>;
    stopTask(taskId: string): Promise<TaskStatus>;
    
    // 系统操作
    getSystemInfo(): Promise<SystemInfo>;
    updateSettings(settings: AppSettings): Promise<boolean>;
} 