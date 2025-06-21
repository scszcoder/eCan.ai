import { logger } from '../../utils/logger';

// 事件类型定义
export type PageRefreshEventType = 'beforeunload' | 'load' | 'visibilitychange' | 'focus' | 'manual';

// 事件数据接口
export interface PageRefreshEvent {
    type: PageRefreshEventType;
    timestamp: number;
    description: string;
    data?: any;
}

// 事件处理器接口
export interface PageRefreshEventHandler {
    onBeforeUnload?: (event: PageRefreshEvent) => void;
    onReload?: (event: PageRefreshEvent) => void;
    onVisibilityChange?: (event: PageRefreshEvent) => void;
    onFocus?: (event: PageRefreshEvent) => void;
    onManual?: (event: PageRefreshEvent) => void;
}

// 事件总线接口
interface EventBus {
    listeners: Set<(event: PageRefreshEvent) => void>;
    subscribe(listener: (event: PageRefreshEvent) => void): () => void;
    emit(event: PageRefreshEvent): void;
}

// 页面刷新事件总线
class PageRefreshEventBus implements EventBus {
    listeners = new Set<(event: PageRefreshEvent) => void>();

    subscribe(listener: (event: PageRefreshEvent) => void) {
        this.listeners.add(listener);
        return () => this.listeners.delete(listener);
    }

    emit(event: PageRefreshEvent) {
        this.listeners.forEach(listener => listener(event));
    }
}

// 页面刷新服务类
export class PageRefreshService {
    private static instance: PageRefreshService;
    private eventBus: PageRefreshEventBus;
    private isInitialized = false;
    private eventHistory: PageRefreshEvent[] = [];
    private maxHistorySize = 100;

    private constructor() {
        this.eventBus = new PageRefreshEventBus();
    }

    // 单例模式
    public static getInstance(): PageRefreshService {
        if (!PageRefreshService.instance) {
            PageRefreshService.instance = new PageRefreshService();
        }
        return PageRefreshService.instance;
    }

    // 初始化服务
    public initialize(): void {
        if (this.isInitialized) {
            logger.warn('PageRefreshService 已经初始化过了');
            return;
        }

        logger.info('初始化 PageRefreshService...');
        this.setupEventListeners();
        this.isInitialized = true;
        logger.info('PageRefreshService 初始化完成');
    }

    // 设置事件监听器
    private setupEventListeners(): void {
        // 监听页面即将刷新事件
        const handleBeforeUnload = (event: BeforeUnloadEvent) => {
            const pageEvent: PageRefreshEvent = {
                type: 'beforeunload',
                timestamp: Date.now(),
                description: '页面即将刷新',
                data: { event }
            };
            this.emitEvent(pageEvent);
            
            // 可选：显示确认对话框
            // event.preventDefault();
            // event.returnValue = '确定要离开页面吗？';
        };

        // 监听页面重新加载完成事件
        const handleLoad = () => {
            const pageEvent: PageRefreshEvent = {
                type: 'load',
                timestamp: Date.now(),
                description: '页面重新加载完成'
            };
            this.emitEvent(pageEvent);
        };

        // 监听页面可见性变化
        const handleVisibilityChange = () => {
            if (document.visibilityState === 'visible') {
                const pageEvent: PageRefreshEvent = {
                    type: 'visibilitychange',
                    timestamp: Date.now(),
                    description: '页面变为可见状态',
                    data: { visibilityState: document.visibilityState }
                };
                this.emitEvent(pageEvent);
            }
        };

        // 监听页面焦点变化
        const handleFocus = () => {
            const pageEvent: PageRefreshEvent = {
                type: 'focus',
                timestamp: Date.now(),
                description: '页面获得焦点'
            };
            this.emitEvent(pageEvent);
        };

        // 添加事件监听器
        window.addEventListener('beforeunload', handleBeforeUnload);
        window.addEventListener('load', handleLoad);
        document.addEventListener('visibilitychange', handleVisibilityChange);
        window.addEventListener('focus', handleFocus);

        // 保存清理函数引用
        this.cleanupFunctions = [
            () => window.removeEventListener('beforeunload', handleBeforeUnload),
            () => window.removeEventListener('load', handleLoad),
            () => document.removeEventListener('visibilitychange', handleVisibilityChange),
            () => window.removeEventListener('focus', handleFocus)
        ];

        logger.info('页面刷新事件监听器设置完成');
    }

    private cleanupFunctions: (() => void)[] = [];

    // 清理事件监听器
    public cleanup(): void {
        if (!this.isInitialized) {
            return;
        }

        logger.info('清理 PageRefreshService...');
        this.cleanupFunctions.forEach(cleanup => cleanup());
        this.cleanupFunctions = [];
        this.isInitialized = false;
        logger.info('PageRefreshService 清理完成');
    }

    // 订阅事件
    public subscribe(handler: PageRefreshEventHandler): () => void {
        const unsubscribe = this.eventBus.subscribe((event: PageRefreshEvent) => {
            switch (event.type) {
                case 'beforeunload':
                    handler.onBeforeUnload?.(event);
                    break;
                case 'load':
                    handler.onReload?.(event);
                    break;
                case 'visibilitychange':
                    handler.onVisibilityChange?.(event);
                    break;
                case 'focus':
                    handler.onFocus?.(event);
                    break;
                case 'manual':
                    handler.onManual?.(event);
                    break;
            }
        });

        return unsubscribe;
    }

    // 手动触发事件
    public manualRefresh(description?: string, data?: any): void {
        const pageEvent: PageRefreshEvent = {
            type: 'manual',
            timestamp: Date.now(),
            description: description || '手动触发重新渲染',
            data
        };
        this.emitEvent(pageEvent);
    }

    // 发送事件
    private emitEvent(event: PageRefreshEvent): void {
        // 添加到历史记录
        this.addToHistory(event);
        
        // 记录日志
        logger.info(`页面刷新事件: ${event.description}`, event);
        
        // 发送到事件总线
        this.eventBus.emit(event);
    }

    // 添加到历史记录
    private addToHistory(event: PageRefreshEvent): void {
        this.eventHistory.unshift(event);
        if (this.eventHistory.length > this.maxHistorySize) {
            this.eventHistory = this.eventHistory.slice(0, this.maxHistorySize);
        }
    }

    // 获取事件历史
    public getEventHistory(): PageRefreshEvent[] {
        return [...this.eventHistory];
    }

    // 清空事件历史
    public clearEventHistory(): void {
        this.eventHistory = [];
        logger.info('事件历史已清空');
    }

    // 获取服务状态
    public getStatus(): { isInitialized: boolean; eventCount: number } {
        return {
            isInitialized: this.isInitialized,
            eventCount: this.eventHistory.length
        };
    }

    // 设置最大历史记录大小
    public setMaxHistorySize(size: number): void {
        this.maxHistorySize = Math.max(1, size);
        if (this.eventHistory.length > this.maxHistorySize) {
            this.eventHistory = this.eventHistory.slice(0, this.maxHistorySize);
        }
    }
}

// 导出单例实例
export const pageRefreshService = PageRefreshService.getInstance(); 