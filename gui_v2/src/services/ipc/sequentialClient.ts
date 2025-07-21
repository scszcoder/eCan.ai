/**
 * Sequential IPC Client
 * 提供一个保证请求处理顺序的 IPC 客户端封装。
 * 所有请求都会被立即发送到后端并行处理，但前端对结果的处理会严格按照请求发出的顺序执行。
 */
import { IPCWCClient } from './ipcWCClient';
import { logger } from '../../utils/logger';

export class SequentialIPCClient {
    private ipcClient: IPCWCClient;
    // Promise 链的末端，确保下一个任务在前一个任务的 Promise 完成后才开始处理结果
    private requestChain: Promise<any>;

    constructor() {
        this.ipcClient = IPCWCClient.getInstance();
        this.requestChain = Promise.resolve();
    }

    /**
     * 发送一个需要保证顺序的请求。
     * @param method 方法名
     * @param params 参数
     * @param timeout 超时时间
     * @returns 一个 Promise，它将在轮到自己时，以正确的顺序解析出结果。
     */
    public sendRequest(method: string, params?: unknown, timeout?: number): Promise<any> {
        // 创建一个新的 Promise，它将在链条的末端执行
        const newRequestPromise = new Promise((resolve, reject) => {
            // 使用 then 将当前请求挂载到 Promise 链的末尾
            this.requestChain.then(() => {
                logger.info(`Processing queued request: ${method}`);
                // 轮到当前请求处理时，才真正调用底层的 sendRequest
                this.ipcClient.sendRequest(method, params, timeout)
                    .then(resolve)
                    .catch(reject);
            });
        });

        // 重要：更新链条的末端为当前这个新的 Promise
        // 这样，下一个请求就会挂载到当前这个请求的后面
        this.requestChain = newRequestPromise;

        return newRequestPromise;
    }
} 