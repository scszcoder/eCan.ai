import { eventBus } from '@/utils/eventBus';
import { logger } from '@/utils/logger';
import { Message } from '../types/chat';

class MessageManager {
  private listeners: Set<(messages: Map<string, Message[]>) => void> = new Set();
  private messages: Map<string, Message[]> = new Map(); // chatId -> messages[]
  private unreadCounts: Map<string, number> = new Map(); // chatId -> unread count

  constructor() {
    this.initEventListeners();
  }

  private initEventListeners() {
    eventBus.on('chat:newMessage', (params: any) => {
      // logger.info('MessageManager received chat:newMessage event:', params);
      
      const { chatId, message } = params;
      const realChatId = chatId || message.chatId;
      
      if (!realChatId) {
        logger.warn('MessageManager: No chatId provided in newMessage event');
        return;
      }

      this.addMessage(realChatId, message);
    });
  }

  private addMessage(chatId: string, message: Message) {
    const chatMessages = this.messages.get(chatId) || [];
    
    // 改进的去重检查：基于多个字段进行更精确的匹配
    const isDuplicate = chatMessages.some((m: Message) => {
      // 1. 检查 ID 是否相同
      if (m.id === message.id) return true;
      
      // 2. 检查是否是同一时间发送的相同内容（时间窗口：5秒内）
      const timeDiff = Math.abs((m.createAt || 0) - (message.createAt || 0));
      const isSameTime = timeDiff < 5000; // 5秒内
      const isSameContent = JSON.stringify(m.content) === JSON.stringify(message.content);
      const isSameSender = m.senderId === message.senderId;
      
      if (isSameTime && isSameContent && isSameSender) return true;
      
      // 3. 检查是否是乐观更新的消息（通过 ID 前缀判断）
      if (m.id.startsWith('user_msg_') && message.id.startsWith('user_msg_')) {
        const mTime = parseInt(m.id.split('_')[2]) || 0;
        const msgTime = parseInt(message.id.split('_')[2]) || 0;
        const timeDiff = Math.abs(mTime - msgTime);
        if (timeDiff < 1000 && isSameContent && isSameSender) return true;
      }
      
      return false;
    });
    
    if (isDuplicate) {
      logger.debug('MessageManager: message already exists, skip:', message.id);
      return;
    }
    
    // 确保新消息有唯一的 id
    const newMessage = {
      ...message,
      id: message.id || `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
    };
    
    // 添加到消息列表
    chatMessages.push(newMessage);
    this.messages.set(chatId, chatMessages);
    
    // 更新未读计数（如果不是当前活跃聊天）
    this.updateUnreadCount(chatId);
    
    this.notifyListeners();
  }

  private updateUnreadCount(chatId: string) {
    const currentCount = this.unreadCounts.get(chatId) || 0;
    this.unreadCounts.set(chatId, currentCount + 1);
  }

  private notifyListeners() {
    this.listeners.forEach(listener => {
      try {
        listener(new Map(this.messages));
      } catch (error) {
        logger.error('Error in message listener:', error);
      }
    });
  }

  // 订阅消息更新
  subscribe(listener: (messages: Map<string, Message[]>) => void): () => void {
    this.listeners.add(listener);
    
    // 立即通知当前状态
    listener(new Map(this.messages));
    
    // 返回取消订阅函数
    return () => {
      this.listeners.delete(listener);
    };
  }

  // 获取指定聊天的消息
  getMessages(chatId: string): Message[] {
    return this.messages.get(chatId) || [];
  }

  // 获取所有消息
  getAllMessages(): Map<string, Message[]> {
    return new Map(this.messages);
  }

  // 获取未读消息数
  getUnreadCount(chatId: string): number {
    return this.unreadCounts.get(chatId) || 0;
  }

  // 获取所有未读消息数
  getAllUnreadCounts(): Map<string, number> {
    return new Map(this.unreadCounts);
  }

  // 标记聊天为已读
  markAsRead(chatId: string): void {
    this.unreadCounts.set(chatId, 0);
  }

  // 设置聊天消息（用于初始化或更新）
  setMessages(chatId: string, messages: Message[]): void {
    this.messages.set(chatId, messages);
    this.notifyListeners();
  }

  // 添加消息到聊天（用于发送新消息时）
  addMessageToChat(chatId: string, message: Message): void {
    const chatMessages = this.messages.get(chatId) || [];
    
    // 改进的去重检查：基于多个字段进行更精确的匹配
    const isDuplicate = chatMessages.some((m: Message) => {
      // 1. 检查 ID 是否相同
      if (m.id === message.id) return true;
      
      // 2. 检查是否是同一时间发送的相同内容（时间窗口：5秒内）
      const timeDiff = Math.abs((m.createAt || 0) - (message.createAt || 0));
      const isSameTime = timeDiff < 5000; // 5秒内
      const isSameContent = JSON.stringify(m.content) === JSON.stringify(message.content);
      const isSameSender = m.senderId === message.senderId;
      
      if (isSameTime && isSameContent && isSameSender) return true;
      
      // 3. 检查是否是乐观更新的消息（通过 ID 前缀判断）
      if (m.id.startsWith('user_msg_') && message.id.startsWith('user_msg_')) {
        const mTime = parseInt(m.id.split('_')[2]) || 0;
        const msgTime = parseInt(message.id.split('_')[2]) || 0;
        const timeDiff = Math.abs(mTime - msgTime);
        if (timeDiff < 1000 && isSameContent && isSameSender) return true;
      }
      
      return false;
    });
    
    if (isDuplicate) {
      logger.debug('MessageManager: message already exists, skip:', message.id);
      return;
    }
    
    // 确保新消息有唯一的 id
    const newMessage = {
      ...message,
      id: message.id || `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
    };
    
    // 添加到消息列表
    chatMessages.push(newMessage);
    this.messages.set(chatId, chatMessages);
    
    this.notifyListeners();
  }

  // 更新消息（用于更新现有消息的状态）
  updateMessage(chatId: string, messageId: string, updates: Partial<Message>): void {
    const chatMessages = this.messages.get(chatId) || [];
    const updatedMessages = chatMessages.map(message => 
      message.id === messageId ? { ...message, ...updates } : message
    );
    this.messages.set(chatId, updatedMessages);
    this.notifyListeners();
  }

  // 清空指定聊天的消息
  clearMessages(chatId: string): void {
    this.messages.delete(chatId);
    this.unreadCounts.delete(chatId);
    this.notifyListeners();
  }

  // 清空所有消息
  clearAll(): void {
    this.messages.clear();
    this.unreadCounts.clear();
    this.notifyListeners();
  }
}

// 创建全局单例
export const messageManager = new MessageManager(); 