import { eventBus } from '@/utils/eventBus';
import { logger } from '@/utils/logger';
import { Message } from '../types/chat';
import { addMessageToList, updateMessageInList, sortMessagesByTime } from '../utils/messageHandlers';

class MessageManager {
  private listeners: Set<(messages: Map<string, Message[]>) => void> = new Set();
  private messages: Map<string, Message[]> = new Map(); // chatId -> messages[]
  private unreadCounts: Map<string, number> = new Map(); // chatId -> unread count
  private chatAccessOrder: string[] = []; // LRU 追踪聊天访问顺序
  
  // 内存限制配置
  private readonly maxMessagesPerChat = 500; // 每个聊天最多保存 500 条消息
  private readonly maxChats = 100; // 最多保存 100 个聊天的消息

  constructor() {
    this.initEventListeners();
  }

  private initEventListeners() {
    eventBus.on('chat:newMessage', (params: any) => {
      const { chatId, message } = params;
      const realChatId = chatId || message.chatId;
      
      if (!realChatId) {
        logger.warn('MessageManager: No chatId provided in newMessage event');
        return;
      }

      // 从事件接收的消息需要自动更新未读数
      this.addMessageInternal(realChatId, message, true);
    });
  }

  /**
   * 内部通用的添加消息方法
   * @param chatId 聊天ID
   * @param message 消息对象
   * @param updateUnread 是否更新未读计数
   */
  private addMessageInternal(chatId: string, message: Message, updateUnread: boolean = false) {
    const chatMessages = this.messages.get(chatId) || [];
    
    // 使用共享的处理函数添加消息
    const result = addMessageToList(chatMessages, message);
    
    // 如果是重复消息，则不做处理
    if (result.isDuplicate) {
      return;
    }
    
    // 更新消息列表
    this.messages.set(chatId, sortMessagesByTime(result.messages));
    
    // 更新未读计数（如果需要）
    if (updateUnread) {
      this.updateUnreadCount(chatId);
    }
    
    this.notifyListeners();
    return result.newMessage;
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

  /**
   * 更新聊天访问顺序（LRU）
   */
  private updateAccessOrder(chatId: string): void {
    // 移除旧位置
    const index = this.chatAccessOrder.indexOf(chatId);
    if (index > -1) {
      this.chatAccessOrder.splice(index, 1);
    }
    // 添加到末尾（最新访问）
    this.chatAccessOrder.push(chatId);
  }

  /**
   * 清理最旧的聊天（LRU）
   */
  private evictOldestChat(): void {
    if (this.chatAccessOrder.length > 0) {
      const oldestChatId = this.chatAccessOrder.shift();
      if (oldestChatId) {
        this.messages.delete(oldestChatId);
        this.unreadCounts.delete(oldestChatId);
        logger.debug(`[MessageManager] Evicted old chat ${oldestChatId} from memory (LRU)`);
      }
    }
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
    // 更新访问顺序
    this.updateAccessOrder(chatId);
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
    // 限制单个聊天的消息数量
    const limitedMessages = messages.slice(-this.maxMessagesPerChat);
    
    // 强制排序，保证老→新
    this.messages.set(chatId, sortMessagesByTime(limitedMessages));
    
    // 更新访问顺序
    this.updateAccessOrder(chatId);
    
    // 限制聊天数量（LRU）
    if (this.messages.size > this.maxChats) {
      this.evictOldestChat();
    }
    
    this.notifyListeners();
    
    // 记录内存使用情况
    if (messages.length > this.maxMessagesPerChat) {
      logger.debug(`[MessageManager] Trimmed chat ${chatId} from ${messages.length} to ${this.maxMessagesPerChat} messages`);
    }
  }

  // 添加消息到聊天（用于发送新消息时）
  addMessageToChat(chatId: string, message: Message): void {
    // 调用通用的添加消息方法，但不更新未读计数（因为是自己发送的）
    const chatMessages = this.messages.get(chatId) || [];
    const result = addMessageToList(chatMessages, message);
    // 强制排序，保证老→新
    this.messages.set(chatId, sortMessagesByTime(result.messages));
    this.notifyListeners();
  }

  // 更新消息（用于更新现有消息的状态）
  updateMessage(chatId: string, messageId: string, updates: Partial<Message>): void {
    const chatMessages = this.messages.get(chatId) || [];
    
    // 使用共享的处理函数更新消息
    const updatedMessages = updateMessageInList(chatMessages, messageId, updates);
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