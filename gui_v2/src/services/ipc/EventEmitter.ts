/**
 * 浏览器兼容的事件发射器实现
 */
export class EventEmitter {
    private events: { [key: string]: Array<(...args: unknown[]) => void> } = {};

    /**
     * 添加事件监听器
     * @template T 事件参数类型
     */
    public on<T>(event: string, listener: (arg: T) => void): void {
        if (!this.events[event]) {
            this.events[event] = [];
        }
        this.events[event].push(listener as (...args: unknown[]) => void);
    }

    /**
     * 移除事件监听器
     * @template T 事件参数类型
     */
    public off<T>(event: string, listener: (arg: T) => void): void {
        if (!this.events[event]) return;
        this.events[event] = this.events[event].filter(l => l !== listener);
    }

    /**
     * 触发事件
     * @template T 事件参数类型
     */
    public emit<T>(event: string, arg: T): void {
        if (!this.events[event]) return;
        this.events[event].forEach(listener => {
            try {
                listener(arg);
            } catch (error) {
                console.error(`Error in event listener for ${event}:`, error);
            }
        });
    }

    /**
     * 移除所有事件监听器
     */
    public removeAllListeners(event?: string): void {
        if (event) {
            delete this.events[event];
        } else {
            this.events = {};
        }
    }
} 