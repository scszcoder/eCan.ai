import { eventBus } from '@/utils/eventBus';
import { logger } from '@/utils/logger';

// 允许存储任意 notification 结构
export type Notification = any;

type NotificationListener = (notifications: Notification[]) => void;

class NotificationManager {
  // chatId -> listeners
  private listeners: Map<string, Set<NotificationListener>> = new Map();
  // chatId -> notifications
  private notifications: Map<string, Notification[]> = new Map();
  // chatId -> has new notifications
  private hasNewNotifications: Map<string, boolean> = new Map();

  constructor() {
    this.initEventListeners();
  }

  private initEventListeners() {
    eventBus.on('chat:newNotification', (params: { chatId: string, notification: any }) => {
      const { chatId, notification } = params;
      if (!chatId) {
        logger.warn('NotificationManager: chatId is required for newNotification');
        return;
      }
      // 直接存原始 notification
      this.addNotification(chatId, notification);
    });
  }

  private addNotification(chatId: string, notification: Notification) {
    const list = this.notifications.get(chatId) || [];
    list.unshift(notification);
    this.notifications.set(chatId, list);
    this.hasNewNotifications.set(chatId, true);
    this.notifyListeners(chatId);
  }

  private notifyListeners(chatId: string) {
    const listeners = this.listeners.get(chatId);
    if (!listeners) return;
    const notifications = this.notifications.get(chatId) || [];
    listeners.forEach(listener => {
      try {
        listener([...notifications]);
      } catch (error) {
        logger.error('Error in notification listener:', error);
      }
    });
  }

  // 订阅指定 chatId 的通知更新
  subscribe(chatId: string, listener: NotificationListener): () => void {
    if (!this.listeners.has(chatId)) {
      this.listeners.set(chatId, new Set());
    }
    this.listeners.get(chatId)!.add(listener);
    // 立即通知当前状态
    listener([... (this.notifications.get(chatId) || [])]);
    // 返回取消订阅函数
    return () => {
      this.listeners.get(chatId)?.delete(listener);
    };
  }

  // 获取指定 chatId 的所有通知
  getNotifications(chatId: string): Notification[] {
    return [...(this.notifications.get(chatId) || [])];
  }

  // 检查指定 chatId 是否有新通知
  hasNew(chatId: string): boolean {
    return !!this.hasNewNotifications.get(chatId);
  }

  // 标记指定 chatId 的通知为已读
  markAsRead(chatId: string): void {
    this.hasNewNotifications.set(chatId, false);
  }

  // 清空指定 chatId 的所有通知
  clear(chatId: string): void {
    this.notifications.set(chatId, []);
    this.hasNewNotifications.set(chatId, false);
    this.notifyListeners(chatId);
  }

  // 移除指定 chatId 的特定通知
  removeNotification(chatId: string, id: string): void {
    const list = this.notifications.get(chatId) || [];
    this.notifications.set(chatId, list.filter((n: any) => n.id !== id));
    this.notifyListeners(chatId);
  }
}

export const notificationManager = new NotificationManager(); 