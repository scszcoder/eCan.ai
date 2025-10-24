/**
 * ChatStateManager - 管理 Chat 页面的状态持久化
 * 
 * 功能：
 * 1. 保存和恢复选中的聊天 ID
 * 2. 保存和恢复每个聊天的滚动位置
 * 3. 在页面跳转时保持状态
 */

interface ChatScrollState {
  scrollTop: number;
  scrollHeight: number;
  timestamp: number;
}

interface ChatPageState {
  activeChatId: string | null;
  agentId: string | null;
  scrollStates: Record<string, ChatScrollState>;
  timestamp: number;
}

const STORAGE_KEY_PREFIX = 'chat_page_state';
const SCROLL_STATE_EXPIRY = 30 * 60 * 1000; // 30分钟过期

class ChatStateManager {
  private static instance: ChatStateManager;

  private constructor() {}

  static getInstance(): ChatStateManager {
    if (!ChatStateManager.instance) {
      ChatStateManager.instance = new ChatStateManager();
    }
    return ChatStateManager.instance;
  }

  /**
   * 获取存储键
   */
  private getStorageKey(userId: string): string {
    return `${STORAGE_KEY_PREFIX}_${userId}`;
  }

  /**
   * 保存完整的页面状态
   */
  savePageState(userId: string, state: Partial<ChatPageState>): void {
    try {
      const currentState = this.loadPageState(userId) || {
        activeChatId: null,
        agentId: null,
        scrollStates: {},
        timestamp: Date.now()
      };

      const newState: ChatPageState = {
        ...currentState,
        ...state,
        timestamp: Date.now()
      };

      sessionStorage.setItem(
        this.getStorageKey(userId),
        JSON.stringify(newState)
      );
    } catch (error) {
      console.warn('[ChatStateManager] Failed to save page state:', error);
    }
  }

  /**
   * 加载完整的页面状态
   */
  loadPageState(userId: string): ChatPageState | null {
    try {
      const stored = sessionStorage.getItem(this.getStorageKey(userId));
      if (!stored) {
        return null;
      }

      const state: ChatPageState = JSON.parse(stored);
      
      // 检查是否过期（超过1小时）
      const isExpired = Date.now() - state.timestamp > 60 * 60 * 1000;
      if (isExpired) {
        this.clearPageState(userId);
        return null;
      }

      return state;
    } catch (error) {
      console.warn('[ChatStateManager] Failed to load page state:', error);
      return null;
    }
  }

  /**
   * 清除页面状态
   */
  clearPageState(userId: string): void {
    try {
      sessionStorage.removeItem(this.getStorageKey(userId));
    } catch (error) {
      console.warn('[ChatStateManager] Failed to clear page state:', error);
    }
  }

  /**
   * 保存活动聊天ID
   */
  saveActiveChatId(userId: string, chatId: string | null, agentId: string | null = null): void {
    this.savePageState(userId, { 
      activeChatId: chatId,
      agentId: agentId
    });
  }

  /**
   * 获取活动聊天ID
   */
  getActiveChatId(userId: string): string | null {
    const state = this.loadPageState(userId);
    return state?.activeChatId || null;
  }

  /**
   * 保存聊天滚动位置
   */
  saveScrollPosition(userId: string, chatId: string, scrollTop: number, scrollHeight: number): void {
    try {
      const state = this.loadPageState(userId) || {
        activeChatId: null,
        agentId: null,
        scrollStates: {},
        timestamp: Date.now()
      };

      state.scrollStates[chatId] = {
        scrollTop,
        scrollHeight,
        timestamp: Date.now()
      };

      this.savePageState(userId, state);
    } catch (error) {
      console.warn('[ChatStateManager] Failed to save scroll position:', error);
    }
  }

  /**
   * 获取聊天滚动位置
   */
  getScrollPosition(userId: string, chatId: string): ChatScrollState | null {
    try {
      const state = this.loadPageState(userId);
      if (!state || !state.scrollStates[chatId]) return null;

      const scrollState = state.scrollStates[chatId];
      
      // 检查滚动状态是否过期
      const isExpired = Date.now() - scrollState.timestamp > SCROLL_STATE_EXPIRY;
      if (isExpired) {
        this.clearScrollPosition(userId, chatId);
        return null;
      }

      return scrollState;
    } catch (error) {
      console.warn('[ChatStateManager] Failed to get scroll position:', error);
      return null;
    }
  }

  /**
   * 清除特定聊天的滚动位置
   */
  clearScrollPosition(userId: string, chatId: string): void {
    try {
      const state = this.loadPageState(userId);
      if (!state) return;

      delete state.scrollStates[chatId];
      this.savePageState(userId, state);
    } catch (error) {
      console.warn('[ChatStateManager] Failed to clear scroll position:', error);
    }
  }

  /**
   * 清除所有过期的滚动状态
   */
  clearExpiredScrollStates(userId: string): void {
    try {
      const state = this.loadPageState(userId);
      if (!state) return;

      const now = Date.now();
      const validScrollStates: Record<string, ChatScrollState> = {};

      Object.entries(state.scrollStates).forEach(([chatId, scrollState]) => {
        if (now - scrollState.timestamp <= SCROLL_STATE_EXPIRY) {
          validScrollStates[chatId] = scrollState;
        }
      });

      state.scrollStates = validScrollStates;
      this.savePageState(userId, state);
    } catch (error) {
      console.warn('[ChatStateManager] Failed to clear expired scroll states:', error);
    }
  }

  /**
   * 保存 Agent ID（过滤器状态）
   */
  saveAgentId(userId: string, agentId: string | null): void {
    this.savePageState(userId, { agentId });
  }

  /**
   * 获取 Agent ID（过滤器状态）
   */
  getAgentId(userId: string): string | null {
    const state = this.loadPageState(userId);
    return state?.agentId || null;
  }
}

export const chatStateManager = ChatStateManager.getInstance();
export type { ChatPageState, ChatScrollState };

