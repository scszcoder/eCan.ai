/**
 * Event Bus - 简单的事件总线实现
 * 用于组件间通信和事件传递
 */

type EventCallback = (data?: any) => void;

class EventBus {
  private events: Map<string, EventCallback[]> = new Map();

  /**
   * 订阅事件
   */
  on(event: string, callback: EventCallback): void {
    if (!this.events.has(event)) {
      this.events.set(event, []);
    }
    this.events.get(event)!.push(callback);
  }

  /**
   * 取消订阅事件
   */
  off(event: string, callback: EventCallback): void {
    const callbacks = this.events.get(event);
    if (callbacks) {
      const index = callbacks.indexOf(callback);
      if (index > -1) {
        callbacks.splice(index, 1);
      }
    }
  }

  /**
   * 发送事件
   */
  emit(event: string, data?: any): void {
    const callbacks = this.events.get(event);
    if (callbacks) {
      callbacks.forEach(callback => {
        try {
          callback(data);
        } catch (error) {
          console.error(`[EventBus] Error in event handler for "${event}":`, error);
        }
      });
    }
  }

  /**
   * 清除所有事件监听器
   */
  clear(): void {
    this.events.clear();
  }

  /**
   * 清除特定事件的所有监听器
   */
  clearEvent(event: string): void {
    this.events.delete(event);
  }
}

// 导出单例
export const eventBus = new EventBus();
