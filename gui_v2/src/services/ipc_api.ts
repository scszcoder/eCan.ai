/**
 * IPC API
 * 提供与 Python Backend通信的Advanced API
 */

import { IPCAPI } from "./ipc/api";


let ipc_api: IPCAPI;

export function set_ipc_api(ii: IPCAPI): void {
    ipc_api = ii;
}

export function get_ipc_api(): IPCAPI {
    return ipc_api;
}

export { ipc_api };

