import { useState, useEffect, useCallback } from 'react';
import { get_ipc_api } from '@/services/ipc_api';
import { ChatNotificationItem } from '../managers/NotificationManager';
import { notificationManager } from '../managers/NotificationManager';

export const NOTIF_PAGE_SIZE = 2;

export const useChatNotifications = (chatId: string, pageSize = NOTIF_PAGE_SIZE, skipInit = false) => {
  const [chatNotificationItems, setChatNotificationItems] = useState<ChatNotificationItem[]>([]);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

  // InitializeLoad第一页
  useEffect(() => {
    console.log('[useChatNotifications] useEffect', { chatId, pageSize, skipInit });
    if (!chatId || skipInit) return;
  }, [chatId, pageSize, skipInit]);

  // 订阅 NotificationManager，推送时自动Refresh
  useEffect(() => {
    if (!chatId) return;
    const unsubscribe = notificationManager.subscribe(chatId, (all) => {
      setChatNotificationItems(all);
      setOffset(all.length);
      setHasMore(true); // 只要有新Data就Allow继续分页
    });
    return unsubscribe;
  }, [chatId]);

  // Load更多（从Backend API 拉取）
  const loadMore = useCallback(async (isInit = false) => {
    if (loadingMore || !hasMore) {
      console.log('[useChatNotifications] loadMore exit: loadingMore or !hasMore', { loadingMore, hasMore });
      return;
    }
    setLoadingMore(true);
    console.log('[useChatNotifications] loadMore start', { chatId, pageSize, offset, isInit });
    const res = await get_ipc_api().chatApi.getChatNotifications({
      chatId,
      limit: pageSize,
      offset: isInit ? 0 : offset,
      reverse: true,
    });
    let newList: ChatNotificationItem[] = [];
    if (res.success && res.data && typeof res.data === 'object' && Array.isArray((res.data as any).data)) {
      newList = (res.data as any).data.map((item: any) => ({ ...item }));
      console.log('[useChatNotifications] API success, newList:', newList);
    } else {
      console.warn('[useChatNotifications] API failed or no data', res);
    }
    // append 到末尾，最新在上，最老在下
    setChatNotificationItems(prev => isInit ? newList : [...prev, ...newList]);
    setOffset(prev => (isInit ? newList.length : prev + newList.length));
    setHasMore(newList.length === pageSize);
    setLoadingMore(false);
    console.log('[useChatNotifications] loadMore end', { newListLen: newList.length, hasMore: newList.length === pageSize });
  }, [chatId, pageSize, offset, hasMore, loadingMore]);

  // 标记为已读（CompatibleExternal调用）
  const markAsRead = () => {
    // 这里Can根据NeedImplementationBackend已读逻辑
    // 目前只做Frontend无Operation，防止External调用报错
    // console.log('[useChatNotifications] markAsRead called');
  };

  // 清空AllNotification（CompatibleExternal调用）
  const clearAll = () => {
    setChatNotificationItems([]);
    setOffset(0);
    setHasMore(true);
    console.log('[useChatNotifications] clearAll called');
  };

  // Remove单条Notification（CompatibleExternal调用）
  const removeChatNotification = (uid: string) => {
    setChatNotificationItems(prev => prev.filter(n => n.uid !== uid));
    console.log('[useChatNotifications] removeChatNotification called', uid);
  };

  return {
    chatNotificationItems,
    hasMore,
    loadMore,
    loadingMore,
    markAsRead,
    clearAll,
    removeChatNotification,
    hasNew: notificationManager.hasNew(chatId), // 新增Field
  };
}; 