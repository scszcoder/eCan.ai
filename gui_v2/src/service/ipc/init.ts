import { IPCService } from './ipcService';

/**
 * 初始化 IPC 服务
 * @returns Promise<boolean> 初始化是否成功
 */
export function initIPC(): Promise<boolean> {
    return new Promise((resolve) => {
        // 检查是否在 Qt WebEngine 环境中
        if (!window.qt?.webChannelTransport) {
            console.warn('Not running in Qt WebEngine environment');
            resolve(false);
            return;
        }

        // 监听 WebChannel 就绪事件
        window.addEventListener('webchannel-ready', () => {
            console.log('WebChannel ready');
            if (window.ipc) {
                console.log('IPC object found after WebChannel initialization');
                // 初始化 IPC 服务
                IPCService.getInstance().init(window.ipc);
                resolve(true);
            } else {
                console.error('IPC object not found after WebChannel initialization');
                resolve(false);
            }
        });

        // 如果 WebChannel 已经就绪，直接初始化
        if (window.ipc) {
            console.log('IPC object found after WebChannel initialization');
            IPCService.getInstance().init(window.ipc);
            resolve(true);
        } else {
            console.log('IPC object not found after WebChannel initialization');
        }
    });
} 