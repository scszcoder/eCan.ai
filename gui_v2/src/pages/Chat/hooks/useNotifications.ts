import { useState, useEffect } from 'react';
import { notificationManager, Notification } from '../managers/NotificationManager';

export const useNotifications = (chatId: string) => {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [hasNew, setHasNew] = useState(false);

  useEffect(() => {
    if (!chatId) return;
    // 订阅指定 chatId 的通知更新
    const unsubscribe = notificationManager.subscribe(chatId, (newNotifications) => {
      setNotifications(newNotifications);
      setHasNew(notificationManager.hasNew(chatId));
    });
    // 清理订阅
    return unsubscribe;
  }, [chatId]);

  const markAsRead = () => {
    notificationManager.markAsRead(chatId);
    setHasNew(false);
  };

  const clearAll = () => {
    notificationManager.clear(chatId);
  };

  const removeNotification = (id: string) => {
    notificationManager.removeNotification(chatId, id);
  };

  return {
    notifications,
    hasNew,
    markAsRead,
    clearAll,
    removeNotification,
  };
}; 