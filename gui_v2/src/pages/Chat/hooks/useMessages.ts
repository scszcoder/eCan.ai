import { useState, useEffect } from 'react';
import { messageManager } from '../managers/MessageManager';
import { Message } from '../types/chat';

export const useMessages = (chatId?: string) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [allMessages, setAllMessages] = useState<Map<string, Message[]>>(new Map());
  const [unreadCounts, setUnreadCounts] = useState<Map<string, number>>(new Map());

  useEffect(() => {
    // 订阅消息更新
    const unsubscribe = messageManager.subscribe((newMessages) => {
      setAllMessages(newMessages);
      
      // 如果指定了 chatId，更新对应的消息
      if (chatId) {
        setMessages(newMessages.get(chatId) || []);
      }
      
      // 更新未读计数
      setUnreadCounts(messageManager.getAllUnreadCounts());
    });

    // 清理订阅
    return unsubscribe;
  }, [chatId]);

  const markAsRead = (targetChatId?: string) => {
    const targetId = targetChatId || chatId;
    if (targetId) {
      messageManager.markAsRead(targetId);
    }
  };

  const updateMessages = (targetChatId: string, newMessages: Message[]) => {
    messageManager.setMessages(targetChatId, newMessages);
  };

  const addMessageToChat = (targetChatId: string, message: Message) => {
    messageManager.addMessageToChat(targetChatId, message);
  };

  const updateMessage = (targetChatId: string, messageId: string, updates: Partial<Message>) => {
    messageManager.updateMessage(targetChatId, messageId, updates);
  };

  const clearMessages = (targetChatId?: string) => {
    const targetId = targetChatId || chatId;
    if (targetId) {
      messageManager.clearMessages(targetId);
    }
  };

  const clearAll = () => {
    messageManager.clearAll();
  };

  const getUnreadCount = (targetChatId?: string) => {
    const targetId = targetChatId || chatId;
    return targetId ? messageManager.getUnreadCount(targetId) : 0;
  };

  return {
    messages,
    allMessages,
    unreadCounts,
    markAsRead,
    updateMessages,
    addMessageToChat,
    updateMessage,
    clearMessages,
    clearAll,
    getUnreadCount,
  };
}; 