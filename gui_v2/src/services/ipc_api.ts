/**
 * IPC API
 * 提供与 Python 后端通信的高级 API
 */


let ipc_api: any = null;

export function set_ipc_api(ii: any): void {
    ipc_api = ii;
}

export function get_ipc_api(): any {
    return ipc_api;
}

export { ipc_api };

