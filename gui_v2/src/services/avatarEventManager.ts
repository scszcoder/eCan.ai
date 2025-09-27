/**
 * Avatar Event Manager
 * Central event system for avatar scene management
 */

import { 
  SceneEvent, 
  SceneEventType, 
  ScenePriority, 
  EventSubscription, 
  SceneEventHandler 
} from '@/types/avatarScene';
import { logger } from '@/utils/logger';
import { logoutManager } from './LogoutManager';

// Event Manager Class
export class AvatarEventManager {
  private subscriptions: Map<string, EventSubscription[]> = new Map();
  private eventQueue: SceneEvent[] = [];
  private isProcessing = false;
  private eventIdCounter = 0;
  private processorIntervalId: NodeJS.Timeout | null = null;

  constructor() {
    this.startEventProcessor();
    this.registerLogoutCleanup();
  }

  /**
   * Generate unique event ID
   */
  private generateEventId(): string {
    return `event_${Date.now()}_${++this.eventIdCounter}`;
  }

  /**
   * Subscribe to scene events
   */
  subscribe(
    eventType: SceneEventType,
    handler: SceneEventHandler,
    agentId?: string,
    priority: ScenePriority = ScenePriority.NORMAL
  ): string {
    const subscriptionId = `sub_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    const subscription: EventSubscription = {
      eventType,
      agentId,
      handler,
      priority,
      subscriptionId
    };

    const key = this.getSubscriptionKey(eventType, agentId);
    
    if (!this.subscriptions.has(key)) {
      this.subscriptions.set(key, []);
    }
    
    const subs = this.subscriptions.get(key)!;
    subs.push(subscription);
    
    // Sort by priority (highest first)
    subs.sort((a, b) => b.priority - a.priority);

    logger.debug(`[AvatarEventManager] Subscribed to ${eventType} events`, {
      subscriptionId,
      agentId,
      priority
    });

    return subscriptionId;
  }

  /**
   * Unsubscribe from events
   */
  unsubscribe(subscriptionId: string): boolean {
    for (const [key, subs] of this.subscriptions.entries()) {
      const index = subs.findIndex(sub => sub.subscriptionId === subscriptionId);
      if (index !== -1) {
        subs.splice(index, 1);
        if (subs.length === 0) {
          this.subscriptions.delete(key);
        }
        logger.debug(`[AvatarEventManager] Unsubscribed ${subscriptionId}`);
        return true;
      }
    }
    return false;
  }

  /**
   * Emit a scene event
   */
  emit(
    type: SceneEventType,
    agentId: string,
    data?: any,
    priority: ScenePriority = ScenePriority.NORMAL,
    source?: string
  ): string {
    const event: SceneEvent = {
      type,
      agentId,
      data,
      timestamp: Date.now(),
      priority,
      eventId: this.generateEventId(),
      source
    };

    this.eventQueue.push(event);
    
    // Sort queue by priority (highest first)
    this.eventQueue.sort((a, b) => b.priority - a.priority);

    logger.debug(`[AvatarEventManager] Event emitted`, {
      type,
      agentId,
      eventId: event.eventId,
      priority,
      queueSize: this.eventQueue.length
    });

    return event.eventId;
  }

  /**
   * Emit timer event (convenience method)
   */
  emitTimer(agentId: string, duration: number, data?: any): string {
    return this.emit('timer', agentId, { duration, ...data }, ScenePriority.LOW, 'timer');
  }

  /**
   * Emit action event (convenience method)
   */
  emitAction(agentId: string, action: string, data?: any): string {
    return this.emit('action', agentId, { action, ...data }, ScenePriority.NORMAL, 'action');
  }

  /**
   * Emit thought change event (convenience method)
   */
  emitThoughtChange(agentId: string, thought: string, data?: any): string {
    return this.emit('thought-change', agentId, { thought, ...data }, ScenePriority.NORMAL, 'thought');
  }

  /**
   * Emit error event (convenience method)
   */
  emitError(agentId: string, error: string | Error, data?: any): string {
    const errorData = {
      error: error instanceof Error ? error.message : error,
      stack: error instanceof Error ? error.stack : undefined,
      ...data
    };
    return this.emit('error', agentId, errorData, ScenePriority.HIGH, 'error');
  }

  /**
   * Emit interaction event (convenience method)
   */
  emitInteraction(agentId: string, interactionType: string, data?: any): string {
    return this.emit('interaction', agentId, { interactionType, ...data }, ScenePriority.NORMAL, 'interaction');
  }

  /**
   * Emit status change event (convenience method)
   */
  emitStatusChange(agentId: string, oldStatus: string, newStatus: string, data?: any): string {
    return this.emit('status-change', agentId, { oldStatus, newStatus, ...data }, ScenePriority.NORMAL, 'status');
  }

  /**
   * Get subscription key
   */
  private getSubscriptionKey(eventType: SceneEventType, agentId?: string): string {
    return agentId ? `${eventType}:${agentId}` : `${eventType}:*`;
  }

  /**
   * Process event queue
   */
  private async processEventQueue(): Promise<void> {
    if (this.isProcessing || this.eventQueue.length === 0) {
      return;
    }

    this.isProcessing = true;

    try {
      while (this.eventQueue.length > 0) {
        const event = this.eventQueue.shift()!;
        await this.processEvent(event);
      }
    } catch (error) {
      logger.error('[AvatarEventManager] Error processing event queue', error);
    } finally {
      this.isProcessing = false;
    }
  }

  /**
   * Process individual event
   */
  private async processEvent(event: SceneEvent): Promise<void> {
    try {
      // Get specific subscriptions for this agent
      const specificKey = this.getSubscriptionKey(event.type, event.agentId);
      const specificSubs = this.subscriptions.get(specificKey) || [];

      // Get global subscriptions for this event type
      const globalKey = this.getSubscriptionKey(event.type);
      const globalSubs = this.subscriptions.get(globalKey) || [];

      // Combine and sort by priority
      const allSubs = [...specificSubs, ...globalSubs]
        .sort((a, b) => b.priority - a.priority);

      logger.debug(`[AvatarEventManager] Processing event ${event.eventId}`, {
        type: event.type,
        agentId: event.agentId,
        subscriberCount: allSubs.length
      });

      // Execute handlers
      for (const subscription of allSubs) {
        try {
          await subscription.handler(event);
        } catch (error) {
          logger.error(`[AvatarEventManager] Error in event handler ${subscription.subscriptionId}`, error);
        }
      }
    } catch (error) {
      logger.error(`[AvatarEventManager] Error processing event ${event.eventId}`, error);
    }
  }

  /**
   * Start event processor
   */
  private startEventProcessor(): void {
    this.processorIntervalId = setInterval(() => {
      this.processEventQueue();
    }, 16); // ~60fps processing
  }

  /**
   * Stop event processor
   */
  private stopEventProcessor(): void {
    if (this.processorIntervalId) {
      clearInterval(this.processorIntervalId);
      this.processorIntervalId = null;
      logger.debug('[AvatarEventManager] Event processor stopped');
    }
  }

  /**
   * Register logout cleanup function
   */
  private registerLogoutCleanup(): void {
    logoutManager.registerCleanup({
      name: 'AvatarEventManager',
      cleanup: () => {
        logger.info('[AvatarEventManager] Cleaning up for logout...');
        this.stopEventProcessor();
        this.clearQueue();
        this.subscriptions.clear();
        this.isProcessing = false;
        this.eventIdCounter = 0;
        logger.info('[AvatarEventManager] Cleanup completed');
      },
      priority: 15 // 较低优先级，让其他组件先清理
    });
  }

  /**
   * Get current queue size
   */
  getQueueSize(): number {
    return this.eventQueue.length;
  }

  /**
   * Clear event queue
   */
  clearQueue(): void {
    this.eventQueue.length = 0;
    logger.debug('[AvatarEventManager] Event queue cleared');
  }

  /**
   * Get subscription count
   */
  getSubscriptionCount(): number {
    let count = 0;
    for (const subs of this.subscriptions.values()) {
      count += subs.length;
    }
    return count;
  }

  /**
   * Get debug info
   */
  getDebugInfo(): any {
    return {
      queueSize: this.eventQueue.length,
      subscriptionCount: this.getSubscriptionCount(),
      subscriptionKeys: Array.from(this.subscriptions.keys()),
      isProcessing: this.isProcessing
    };
  }
}

// Global instance
export const avatarEventManager = new AvatarEventManager();

// Convenience exports
export const {
  subscribe: subscribeToSceneEvents,
  unsubscribe: unsubscribeFromSceneEvents,
  emit: emitSceneEvent,
  emitTimer,
  emitAction,
  emitThoughtChange,
  emitError,
  emitInteraction,
  emitStatusChange
} = avatarEventManager;
