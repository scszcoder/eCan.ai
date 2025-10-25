/**
 * ChatStateManager - 管理 Chat 页面的跨会话状态持久化
 * 
 * 注意：由于 Chat 页面已启用 KeepAlive，大部分状态（如选中的聊天、滚动位置等）
 * 会自动保持，不需要手动管理。此管理器只负责需要跨会话持久化的状态。
 * 
 * 功能：
 * 1. 保存和恢复 Agent 过滤器状态（需要跨会话保持）
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
   * 获取存储键
   */
  private getStorageKey(userId: string): string {
    return `${STORAGE_KEY_PREFIX}_${userId}`;
  }

  /**
   * 保存页面状态
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
   * 加载页面状态
   */
  private loadPageState(userId: string): ChatPageState | null {
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
export type { ChatPageState };

