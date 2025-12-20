import { eventBus } from '@/utils/eventBus';
import { logger } from '@/utils/logger';
import { Message } from '../types/chat';
import { addMessageToList, updateMessageInList, sortMessagesByTime } from '../utils/messageHandlers';

class MessageManager {
  private listeners: Set<(messages: Map<string, Message[]>) => void> = new Set();
  private messages: Map<string, Message[]> = new Map(); // chatId -> messages[]
  private unreadCounts: Map<string, number> = new Map(); // chatId -> unread count
  private chatAccessOrder: string[] = []; // LRU 追踪聊天访问顺序
  private activeChatId: string | null = null; // Track currently active chat
  
  // 内存LimitConfiguration
  private readonly maxMessagesPerChat = 500; // 每个聊天最多Save 500 条Message
  private readonly maxChats = 100; // 最多Save 100 个聊天的Message

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

      // 从EventReceive的MessageNeed自动Update未读数
      this.addMessageInternal(realChatId, message, true);
    });
  }

  /**
   * InternalGeneral的AddMessageMethod
   * @param chatId 聊天ID
   * @param message Message对象
   * @param updateUnread 是否Update未读计数
   */
  private addMessageInternal(chatId: string, message: Message, updateUnread: boolean = false) {
    const chatMessages = this.messages.get(chatId) || [];
    
    // 使用共享的ProcessFunctionAddMessage
    const result = addMessageToList(chatMessages, message);
    
    // If是重复Message，则不做Process
    if (result.isDuplicate) {
      return;
    }
    
    // UpdateMessageList
    this.messages.set(chatId, sortMessagesByTime(result.messages));
    
    // Update未读计数（IfNeed）
    if (updateUnread) {
      this.updateUnreadCount(chatId);
    }
    
    this.notifyListeners();
    return result.newMessage;
  }

  private updateUnreadCount(chatId: string) {
    // CRITICAL FIX: Don't increment unread if this is the active chat
    // User is viewing this chat, so they've "read" the message
    if (chatId === this.activeChatId) {
      return;
    }
    
    const currentCount = this.unreadCounts.get(chatId) || 0;
    this.unreadCounts.set(chatId, currentCount + 1);
  }
  
  /**
   * Set the currently active chat
   * When a chat is active, new messages won't increase unread count
   */
  setActiveChat(chatId: string | null): void {
    this.activeChatId = chatId;
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
   * Update聊天访问顺序（LRU）
   */
  private updateAccessOrder(chatId: string): void {
    // Remove旧Position
    const index = this.chatAccessOrder.indexOf(chatId);
    if (index > -1) {
      this.chatAccessOrder.splice(index, 1);
    }
    // Add到末尾（最新访问）
    this.chatAccessOrder.push(chatId);
  }

  /**
   * Cleanup最旧的聊天（LRU）
   */
  private evictOldestChat(): void {
    if (this.chatAccessOrder.length > 0) {
      const oldestChatId = this.chatAccessOrder.shift();
      if (oldestChatId) {
        this.messages.delete(oldestChatId);
        this.unreadCounts.delete(oldestChatId);
      }
    }
  }

  // 订阅MessageUpdate
  subscribe(listener: (messages: Map<string, Message[]>) => void): () => void {
    this.listeners.add(listener);
    
    // 立即NotificationWhen前Status
    listener(new Map(this.messages));
    
    // 返回Cancel订阅Function
    return () => {
      this.listeners.delete(listener);
    };
  }

  // Get指定聊天的Message
  getMessages(chatId: string): Message[] {
    // Update访问顺序
    this.updateAccessOrder(chatId);
    return this.messages.get(chatId) || [];
  }

  // GetAllMessage
  getAllMessages(): Map<string, Message[]> {
    return new Map(this.messages);
  }

  // Get未读Message数
  getUnreadCount(chatId: string): number {
    return this.unreadCounts.get(chatId) || 0;
  }

  // GetAll未读Message数
  getAllUnreadCounts(): Map<string, number> {
    return new Map(this.unreadCounts);
  }

  // 标记聊天为已读
  markAsRead(chatId: string): void {
    this.unreadCounts.set(chatId, 0);
    this.notifyListeners(); // Notify subscribers so UI updates immediately
  }

  // Settings聊天Message（Used forInitialize或Update）
  setMessages(chatId: string, messages: Message[]): void {
    // Limit单个聊天的MessageCount
    const limitedMessages = messages.slice(-this.maxMessagesPerChat);
    
    // 强制Sort，保证老→新
    this.messages.set(chatId, sortMessagesByTime(limitedMessages));
    
    // Update访问顺序
    this.updateAccessOrder(chatId);
    
    // Limit聊天Count（LRU）
    if (this.messages.size > this.maxChats) {
      this.evictOldestChat();
    }
    
    this.notifyListeners();
    
    // 记录内存使用情况
    // Trim messages if exceeding max limit (handled silently)
  }

  // AddMessage到聊天（Used forSend新Message时）
  addMessageToChat(chatId: string, message: Message): void {
    // 调用General的AddMessageMethod，但不Update未读计数（因为是自己Send的）
    const chatMessages = this.messages.get(chatId) || [];
    const result = addMessageToList(chatMessages, message);
    // 强制Sort，保证老→新
    this.messages.set(chatId, sortMessagesByTime(result.messages));
    this.notifyListeners();
  }

  // UpdateMessage（Used forUpdate现有Message的Status）
  updateMessage(chatId: string, messageId: string, updates: Partial<Message>): void {
    const chatMessages = this.messages.get(chatId) || [];
    
    // 使用共享的ProcessFunctionUpdateMessage
    const updatedMessages = updateMessageInList(chatMessages, messageId, updates);
    this.messages.set(chatId, updatedMessages);
    
    this.notifyListeners();
  }

  // 清空指定聊天的Message
  clearMessages(chatId: string): void {
    this.messages.delete(chatId);
    this.unreadCounts.delete(chatId);
    this.notifyListeners();
  }

  // 清空AllMessage
  clearAll(): void {
    this.messages.clear();
    this.unreadCounts.clear();
    this.notifyListeners();
  }
}

// Create全局单例
export const messageManager = new MessageManager(); 