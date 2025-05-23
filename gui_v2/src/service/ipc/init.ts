import { IPC } from './types';
import { IPCService } from './ipcService';

/**
 * 初始化 IPC
 */
export async function initIPC(): Promise<void> {
    // 检查是否在 Qt WebEngine 环境中
    if (!window.qt?.webChannelTransport) {
        console.warn('Not running in Qt WebEngine environment');
        return;
    }
    console.log(window.qt?.webChannelTransport);

    // 等待 WebChannel 就绪
    // await checkWebChannel();

    // // 创建 IPC 对象
    // const ipc: IPC = {
    //     web_to_python: async (message: string): Promise<string> => {
    //         return new Promise((resolve, reject) => {
    //             try {
    //                 console.log('Sending message:', message);
    //                 window.qt.webChannelTransport.send(message);
    //                 resolve('');
    //             } catch (error) {
    //                 console.error('Error sending message:', error);
    //                 reject(error);
    //             }
    //         });
    //     }
    // };

    

    // 监听 webchannel-ready 事件
    window.addEventListener('webchannel-ready', () => {
        console.log('WebChannel is ready');
        const ipc: IPC = window.ipc;
        // 初始化 IPC 服务
        const ipcService = IPCService.getInstance();
        ipcService.setIPC(ipc);
        console.log('IPC initialized successfully');
    });
}

// /**
//  * 检查 WebChannel 是否就绪
//  */
// async function checkWebChannel(): Promise<void> {
//     return new Promise((resolve) => {
//         const check = () => {
//             if (window.qt?.webChannelTransport) {
//                 console.log('WebChannel ready');
//                 resolve();
//             } else {
//                 console.log('WebChannel not ready');
//                 setTimeout(check, 100);
//             }
//         };
//         check();
//     });
// } 