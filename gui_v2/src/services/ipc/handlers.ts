import { IPCRequest, IPCResponse, createSuccessResponse, createErrorResponse } from './types';
import { IPCHandlerRegistry } from './handlerRegistry';

// 配置处理器
IPCHandlerRegistry.register('get_config', async (request: IPCRequest, params: unknown): Promise<IPCResponse> => {
    try {
        const { key } = params as { key: string };
        console.log(`[IPC] Getting config for key: ${key}`);
        // TODO: 实现配置获取逻辑
        return createSuccessResponse(request, { key, value: 'Config value' });
    } catch (error) {
        console.error(`[IPC] Error getting config:`, error);
        return createErrorResponse(
            request,
            'CONFIG_ERROR',
            error instanceof Error ? error.message : 'Unknown error'
        );
    }
});

IPCHandlerRegistry.register('set_config', async (request: IPCRequest, params: unknown): Promise<IPCResponse> => {
    try {
        const { key, value } = params as { key: string; value: unknown };
        console.log(`[IPC] Setting config for key: ${key}, value:`, value);
        // TODO: 实现配置设置逻辑
        return createSuccessResponse(request, { success: true });
    } catch (error) {
        console.error(`[IPC] Error setting config:`, error);
        return createErrorResponse(
            request,
            'CONFIG_ERROR',
            error instanceof Error ? error.message : 'Unknown error'
        );
    }
});

// 命令处理器
IPCHandlerRegistry.register('execute_command', async (request: IPCRequest, params: unknown): Promise<IPCResponse> => {
    try {
        const { command, args } = params as { command: string; args?: unknown[] };
        console.log(`[IPC] Executing command: ${command}`, args ? `with args: ${JSON.stringify(args)}` : '');
        // TODO: 实现命令执行逻辑
        return createSuccessResponse(request, { command, result: `Executed command: ${command}` });
    } catch (error) {
        console.error(`[IPC] Error executing command:`, error);
        return createErrorResponse(
            request,
            'COMMAND_ERROR',
            error instanceof Error ? error.message : 'Unknown error'
        );
    }
});

// 事件处理器
IPCHandlerRegistry.register('notify_event', async (request: IPCRequest, params: unknown): Promise<IPCResponse> => {
    try {
        const { event, data } = params as { event: string; data?: unknown };
        console.log(`[IPC] Processing event: ${event}`, data ? `with data: ${JSON.stringify(data)}` : '');
        // TODO: 实现事件处理逻辑
        return createSuccessResponse(request, { event, processed: true });
    } catch (error) {
        console.error(`[IPC] Error processing event:`, error);
        return createErrorResponse(
            request,
            'EVENT_ERROR',
            error instanceof Error ? error.message : 'Unknown error'
        );
    }
}); 