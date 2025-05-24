/**
 * IPC 处理器
 * 实现了与 Python 后端通信的请求处理器
 */
import { IPCRequest } from './types';

/**
 * 处理器上下文
 * 包含处理器执行所需的状态和工具
 */
interface HandlerContext {
    /** 配置存储 */
    config: Map<string, unknown>;
    /** 日志记录器 */
    logger: Console;
}

/**
 * 创建处理器上下文
 * @returns 处理器上下文
 */
function createHandlerContext(): HandlerContext {
    return {
        config: new Map<string, unknown>(),
        logger: console
    };
}

/**
 * 验证请求参数
 * @param request - 请求对象
 * @param requiredParams - 必需参数列表
 * @returns 验证结果
 */
function validateParams(request: IPCRequest, requiredParams: string[]): { valid: boolean; missingParams?: string[] } {
    const params = request.params as Record<string, unknown> | undefined;
    if (!params) {
        return { valid: false, missingParams: requiredParams };
    }

    const missingParams = requiredParams.filter(param => !(param in params));
    return {
        valid: missingParams.length === 0,
        missingParams: missingParams.length > 0 ? missingParams : undefined
    };
}

/**
 * 获取配置处理器
 * @param context - 处理器上下文
 * @returns 请求处理器函数
 */
export function createGetConfigHandler(context: HandlerContext) {
    return async (request: IPCRequest): Promise<unknown> => {
        const validation = validateParams(request, ['key']);
        if (!validation.valid) {
            context.logger.warn('Invalid parameters for get_config:', validation.missingParams);
            throw new Error(`Missing required parameters: ${validation.missingParams?.join(', ')}`);
        }

        const { key } = request.params as { key: string };
        context.logger.debug(`Getting config for key: ${key}`);

        if (!context.config.has(key)) {
            context.logger.warn(`Config not found for key: ${key}`);
            throw new Error(`Config not found for key: ${key}`);
        }

        return context.config.get(key);
    };
}

/**
 * 设置配置处理器
 * @param context - 处理器上下文
 * @returns 请求处理器函数
 */
export function createSetConfigHandler(context: HandlerContext) {
    return async (request: IPCRequest): Promise<unknown> => {
        const validation = validateParams(request, ['key', 'value']);
        if (!validation.valid) {
            context.logger.warn('Invalid parameters for set_config:', validation.missingParams);
            throw new Error(`Missing required parameters: ${validation.missingParams?.join(', ')}`);
        }

        const { key, value } = request.params as { key: string; value: unknown };
        context.logger.debug(`Setting config for key: ${key}`);

        context.config.set(key, value);
        return { success: true };
    };
}

/**
 * 获取所有配置处理器
 * @param context - 处理器上下文
 * @returns 请求处理器函数
 */
export function createGetAllConfigHandler(context: HandlerContext) {
    return async (): Promise<Record<string, unknown>> => {
        context.logger.debug('Getting all configs');
        return Object.fromEntries(context.config);
    };
}

/**
 * 重置配置处理器
 * @param context - 处理器上下文
 * @returns 请求处理器函数
 */
export function createResetConfigHandler(context: HandlerContext) {
    return async (): Promise<unknown> => {
        context.logger.debug('Resetting configs');
        context.config.clear();
        return { success: true };
    };
}

/**
 * 执行命令处理器
 * @param context - 处理器上下文
 * @returns 请求处理器函数
 */
export function createExecuteCommandHandler(context: HandlerContext) {
    return async (request: IPCRequest): Promise<unknown> => {
        const validation = validateParams(request, ['command']);
        if (!validation.valid) {
            context.logger.warn('Invalid parameters for execute_command:', validation.missingParams);
            throw new Error(`Missing required parameters: ${validation.missingParams?.join(', ')}`);
        }

        const { command, args } = request.params as { command: string; args?: unknown[] };
        context.logger.debug(`Executing command: ${command}`, args ? `with args: ${JSON.stringify(args)}` : '');

        // TODO: 实现命令执行逻辑
        return { command, result: `Executed command: ${command}` };
    };
}

/**
 * 事件通知处理器
 * @param context - 处理器上下文
 * @returns 请求处理器函数
 */
export function createNotifyEventHandler(context: HandlerContext) {
    return async (request: IPCRequest): Promise<unknown> => {
        const validation = validateParams(request, ['event']);
        if (!validation.valid) {
            context.logger.warn('Invalid parameters for notify_event:', validation.missingParams);
            throw new Error(`Missing required parameters: ${validation.missingParams?.join(', ')}`);
        }

        const { event, data } = request.params as { event: string; data?: unknown };
        context.logger.debug(`Processing event: ${event}`, data ? `with data: ${JSON.stringify(data)}` : '');

        // TODO: 实现事件处理逻辑
        return { event, processed: true };
    };
}

/**
 * 创建所有处理器
 * @returns 处理器映射
 */
export function createHandlers() {
    const context = createHandlerContext();
    return {
        get_config: createGetConfigHandler(context),
        set_config: createSetConfigHandler(context),
        get_all_config: createGetAllConfigHandler(context),
        reset_config: createResetConfigHandler(context),
        execute_command: createExecuteCommandHandler(context),
        notify_event: createNotifyEventHandler(context)
    };
}