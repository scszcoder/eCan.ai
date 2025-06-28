import { useState, useEffect } from 'react';
import { notificationManager, Notification } from '../managers/NotificationManager';

export const useNotifications = () => {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [hasNew, setHasNew] = useState(false);

  useEffect(() => {
    // 订阅通知更新
    const unsubscribe = notificationManager.subscribe((newNotifications) => {
      setNotifications(newNotifications);
      setHasNew(notificationManager.hasNew());
    });

    // 清理订阅
    return unsubscribe;
  }, []);

  const markAsRead = () => {
    notificationManager.markAsRead();
    setHasNew(false);
  };

  const clearAll = () => {
    notificationManager.clear();
  };

  const removeNotification = (id: string) => {
    notificationManager.removeNotification(id);
  };

  return {
    notifications,
    hasNew,
    markAsRead,
    clearAll,
    removeNotification,
  };
}; 