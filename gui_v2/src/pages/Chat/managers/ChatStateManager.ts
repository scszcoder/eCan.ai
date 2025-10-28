/**
 * ChatStateManager - 管理 Chat Page的跨会话Status持久化
 * 
 * Note：由于 Chat Page已Enabled KeepAlive，大部分Status（如选中的聊天、ScrollPosition等）
 * 会自动保持，不Need手动管理。此管理器只负责Need跨会话持久化的Status。
 * 
 * 功能：
 * 1. Save和Restore Agent Filter器Status（Need跨会话保持）
 */

interface ChatPageState {
  agentId: string | null;
  timestamp: number;
}

const STORAGE_KEY_PREFIX = 'chat_page_state';

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
   * GetStorage键
   */
  private getStorageKey(userId: string): string {
    return `${STORAGE_KEY_PREFIX}_${userId}`;
  }

  /**
   * SavePageStatus
   */
  private savePageState(userId: string, state: Partial<ChatPageState>): void {
    try {
      const currentState = this.loadPageState(userId) || {
        agentId: null,
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
   * LoadPageStatus
   */
  private loadPageState(userId: string): ChatPageState | null {
    try {
      const stored = sessionStorage.getItem(this.getStorageKey(userId));
      if (!stored) {
        return null;
      }

      const state: ChatPageState = JSON.parse(stored);
      
      // Check是否过期（超过1小时）
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
   * 清除PageStatus
   */
  clearPageState(userId: string): void {
    try {
      sessionStorage.removeItem(this.getStorageKey(userId));
    } catch (error) {
      console.warn('[ChatStateManager] Failed to clear page state:', error);
    }
  }

  /**
   * Save Agent ID（Filter器Status）
   */
  saveAgentId(userId: string, agentId: string | null): void {
    this.savePageState(userId, { agentId });
  }

  /**
   * Get Agent ID（Filter器Status）
   */
  getAgentId(userId: string): string | null {
    const state = this.loadPageState(userId);
    return state?.agentId || null;
  }
}

export const chatStateManager = ChatStateManager.getInstance();
export type { ChatPageState };

