/**
 * Event Bus - Simple的Event总线Implementation
 * Used forComponent间通信和Event传递
 */

type EventCallback = (data?: any) => void;

class EventBus {
  private events: Map<string, EventCallback[]> = new Map();

  /**
   * 订阅Event
   */
  on(event: string, callback: EventCallback): void {
    if (!this.events.has(event)) {
      this.events.set(event, []);
    }
    this.events.get(event)!.push(callback);
  }

  /**
   * Cancel订阅Event
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
   * SendEvent
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
   * 清除AllEventListen器
   */
  clear(): void {
    this.events.clear();
  }

  /**
   * 清除特定Event的AllListen器
   */
  clearEvent(event: string): void {
    this.events.delete(event);
  }
}

// Export单例
export const eventBus = new EventBus();
