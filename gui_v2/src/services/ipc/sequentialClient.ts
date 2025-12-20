/**
 * Sequential IPC Client
 * 提供一个保证RequestProcess顺序的 IPC Client封装。
 * AllRequest都会被立即Send到Backend并行Process，但Frontend对Result的Process会严格按照Request发出的顺序Execute。
 */
import { IPCWCClient } from './ipcWCClient';
import { logger } from '../../utils/logger';

export class SequentialIPCClient {
    private ipcClient: IPCWCClient;
    // Promise 链的末端，确保下一个任务在前一个任务的 Promise Completed后才开始ProcessResult
    private requestChain: Promise<any>;

    constructor() {
        this.ipcClient = IPCWCClient.getInstance();
        this.requestChain = Promise.resolve();
    }

    /**
     * Send一个Need保证顺序的Request。
     * @param method Method名
     * @param params Parameter
     * @param timeout TimeoutTime
     * @returns 一个 Promise，它将在轮到自己时，以正确的顺序Parse出Result。
     */
    public sendRequest(method: string, params?: unknown, timeout?: number): Promise<any> {
        // Create一个新的 Promise，它将在链条的末端Execute
        const newRequestPromise = new Promise((resolve, reject) => {
            // 使用 then 将When前RequestMount到 Promise 链的末尾
            this.requestChain.then(() => {
                logger.info(`Processing queued request: ${method}`);
                // 轮到When前RequestProcess时，才真正调用底层的 sendRequest
                this.ipcClient.sendRequest(method, params, timeout)
                    .then(resolve)
                    .catch(reject);
            });
        });

        // 重要：Update链条的末端为When前这个新的 Promise
        // 这样，下一个Request就会Mount到When前这个Request的后面
        this.requestChain = newRequestPromise;

        return newRequestPromise;
    }
} 