import { eventBus } from '@/utils/eventBus';
import { logger } from '@/utils/logger';

// AllowStorage任意 notification 结构
export type Notification = any;

export type ChatNotificationItem = {
  isRead: boolean;
  timestamp: string;
  uid: string;
  content: any;
};

type NotificationListener = (notifications: ChatNotificationItem[]) => void;

class NotificationManager {
  // chatId -> listeners
  private listeners: Map<string, Set<NotificationListener>> = new Map();
  // chatId -> chatNotificationItems
  private chatNotificationItems: Map<string, ChatNotificationItem[]> = new Map();
  // chatId -> has new notifications
  private hasNewNotificationItems: Map<string, boolean> = new Map();

  constructor() {
    this.initEventListeners();
  }

  private initEventListeners() {
    eventBus.on('chat:newNotification', (params: { chatId: string, content: any, isRead: boolean, timestamp: string, uid: string }) => {
      const { chatId, content, isRead, timestamp, uid } = params;

      if (!chatId) {
        logger.warn('NotificationManager: chatId is required for newNotification');
        return;
      }

      // DEBUG: Inspect payload paths and types before storing
      try { console.log('[NotificationManager] newNotification params', { chatId, isRead, timestamp, uid }); } catch {}
      const body: any = (content && typeof content === 'object') ? content : {};
      try { console.log('[NotificationManager] content (top-level) keys', Object.keys(body || {})); } catch {}
      try {
        const nested = body?.content;
        console.log('[NotificationManager] path checks', {
          has_content: !!nested,
          typeof_content: typeof nested,
          has_notification_top: !!body?.notification,
          typeof_notification_top: typeof body?.notification,
          has_notification_nested: !!nested?.notification,
          typeof_notification_nested: typeof nested?.notification,
          items_len: Array.isArray(nested?.notification?.Items) ? nested.notification.Items.length : 'n/a'
        });
      } catch {}
      try {
        const nested = body?.content;
        console.log('[NotificationManager] subfield types', {
          card: typeof nested?.card,
          code: typeof nested?.code,
          form: Array.isArray(nested?.form) ? 'array' : typeof nested?.form,
          notification: typeof nested?.notification,
        });
      } catch {}

      const chatNotificationItem: ChatNotificationItem = {
        isRead: isRead,
        timestamp: timestamp,
        uid: uid,
        content: content,
      };
      this.addNotification(chatId, chatNotificationItem);
    });
  }

  public addNotification(chatId: string, chatNotificationItem: ChatNotificationItem) {
    const list = this.chatNotificationItems.get(chatId) || [];
    list.unshift(chatNotificationItem);
    this.chatNotificationItems.set(chatId, list);
    this.hasNewNotificationItems.set(chatId, true);
    this.notifyListeners(chatId);
  }

  private notifyListeners(chatId: string) {
    const listeners = this.listeners.get(chatId);
    if (!listeners) return;
    const notifications = this.chatNotificationItems.get(chatId) || [];
    listeners.forEach(listener => {
      try {
        listener([...notifications]);
      } catch (error) {
        logger.error('Error in notification listener:', error);
      }
    });
  }

  // 订阅指定 chatId 的NotificationUpdate
  subscribe(chatId: string, listener: NotificationListener): () => void {
    if (!this.listeners.has(chatId)) {
      this.listeners.set(chatId, new Set());
    }
    this.listeners.get(chatId)!.add(listener);
    // 立即NotificationWhen前Status
    listener([...(this.chatNotificationItems.get(chatId) || [])]);
    // 返回Cancel订阅Function
    return () => {
      this.listeners.get(chatId)?.delete(listener);
    };
  }

  // Get指定 chatId 的AllNotification
  getNotifications(chatId: string): ChatNotificationItem[] {
    return [...(this.chatNotificationItems.get(chatId) || [])];
  }

  // Get指定 chatId 的分页Notification
  getNotificationsPaged(chatId: string, offset: number, limit: number): ChatNotificationItem[] {
    const all = this.chatNotificationItems.get(chatId) || [];
    return all.slice(offset, offset + limit);
  }

  // Check指定 chatId 是否有新Notification
  hasNew(chatId: string): boolean {
    return !!this.hasNewNotificationItems.get(chatId);
  }

  // 标记指定 chatId 的Notification为已读
  markAsRead(chatId: string): void {
    this.hasNewNotificationItems.set(chatId, false);
  }

  // 清空指定 chatId 的AllNotification
  clear(chatId: string): void {
    this.chatNotificationItems.set(chatId, []);
    this.hasNewNotificationItems.set(chatId, false);
    this.notifyListeners(chatId);
  }

  // Remove指定 chatId 的特定Notification
  removeNotification(chatId: string, uid: string): void {
    const list = this.chatNotificationItems.get(chatId) || [];
    this.chatNotificationItems.set(chatId, list.filter((n: ChatNotificationItem) => n.uid !== uid));
    this.notifyListeners(chatId);
  }
}

export const notificationManager = new NotificationManager(); 