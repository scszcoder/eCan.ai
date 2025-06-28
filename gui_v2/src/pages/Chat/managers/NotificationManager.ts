import { eventBus } from '@/utils/eventBus';
import { logger } from '@/utils/logger';

export interface Notification {
  id: string;
  title: string;
  content: string;
  time?: string;
  type?: string;
  status?: string;
}

class NotificationManager {
  private listeners: Set<(notifications: Notification[]) => void> = new Set();
  private notifications: Notification[] = [];
  private hasNewNotifications = false;

  constructor() {
    this.initEventListeners();
  }

  private initEventListeners() {
    eventBus.on('chat:newNotification', (params: any) => {
      // logger.info('NotificationManager received chat:newNotification event:', params);
      
      const newNotification: Notification = {
        id: params.id || `notification_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        title: params.title || params.type || 'Agent Notification',
        content: params.content || params.message || JSON.stringify(params),
        time: params.time || new Date().toLocaleString(),
        type: params.type,
        status: params.status
      };

      this.addNotification(newNotification);
    });
  }

  private addNotification(notification: Notification) {
    this.notifications.unshift(notification);
    this.hasNewNotifications = true;
    this.notifyListeners();
  }

  private notifyListeners() {
    this.listeners.forEach(listener => {
      try {
        listener([...this.notifications]);
      } catch (error) {
        logger.error('Error in notification listener:', error);
      }
    });
  }

  // 订阅通知更新
  subscribe(listener: (notifications: Notification[]) => void): () => void {
    this.listeners.add(listener);
    
    // 立即通知当前状态
    listener([...this.notifications]);
    
    // 返回取消订阅函数
    return () => {
      this.listeners.delete(listener);
    };
  }

  // 获取所有通知
  getNotifications(): Notification[] {
    return [...this.notifications];
  }

  // 检查是否有新通知
  hasNew(): boolean {
    return this.hasNewNotifications;
  }

  // 标记通知为已读
  markAsRead(): void {
    this.hasNewNotifications = false;
  }

  // 清空所有通知
  clear(): void {
    this.notifications = [];
    this.hasNewNotifications = false;
    this.notifyListeners();
  }

  // 移除特定通知
  removeNotification(id: string): void {
    this.notifications = this.notifications.filter(n => n.id !== id);
    this.notifyListeners();
  }
}

// 创建全局单例
export const notificationManager = new NotificationManager(); 