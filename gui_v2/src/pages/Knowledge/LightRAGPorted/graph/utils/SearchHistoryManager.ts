/**
 * 搜索历史管理器
 * 用于管理图标签搜索的历史记录和热门标签
 */

const STORAGE_KEY = 'lightrag_graph_search_history';
const MAX_HISTORY_ITEMS = 50;

interface HistoryItem {
  label: string;
  timestamp: number;
  frequency: number;
}

class SearchHistoryManagerClass {
  private history: HistoryItem[] = [];

  constructor() {
    this.loadHistory();
  }

  /**
   * 从 localStorage 加载历史记录
   */
  private loadHistory(): void {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        this.history = JSON.parse(stored);
      }
    } catch (error) {
      console.error('Failed to load search history:', error);
      this.history = [];
    }
  }

  /**
   * 保存历史记录到 localStorage
   */
  private saveHistory(): void {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(this.history));
    } catch (error) {
      console.error('Failed to save search history:', error);
    }
  }

  /**
   * 添加标签到历史记录
   */
  addToHistory(label: string): void {
    if (!label || label.trim() === '' || label === '*') {
      return;
    }

    const normalizedLabel = label.trim();
    const existingIndex = this.history.findIndex(item => item.label === normalizedLabel);

    if (existingIndex >= 0) {
      // 更新现有项：增加频率和更新时间戳
      this.history[existingIndex].frequency += 1;
      this.history[existingIndex].timestamp = Date.now();
    } else {
      // 添加新项
      this.history.push({
        label: normalizedLabel,
        timestamp: Date.now(),
        frequency: 1
      });
    }

    // 限制历史记录数量
    if (this.history.length > MAX_HISTORY_ITEMS) {
      // 按频率和时间排序，移除最不常用的
      this.history.sort((a, b) => {
        if (b.frequency !== a.frequency) {
          return b.frequency - a.frequency;
        }
        return b.timestamp - a.timestamp;
      });
      this.history = this.history.slice(0, MAX_HISTORY_ITEMS);
    }

    this.saveHistory();
  }

  /**
   * 获取历史记录标签列表（按频率和时间排序）
   */
  getHistoryLabels(limit?: number): string[] {
    const sorted = [...this.history].sort((a, b) => {
      // 优先按频率排序
      if (b.frequency !== a.frequency) {
        return b.frequency - a.frequency;
      }
      // 频率相同则按时间排序
      return b.timestamp - a.timestamp;
    });

    const labels = sorted.map(item => item.label);
    return limit ? labels.slice(0, limit) : labels;
  }

  /**
   * 获取完整历史记录
   */
  getHistory(): HistoryItem[] {
    return [...this.history];
  }

  /**
   * 清空历史记录
   */
  clearHistory(): void {
    this.history = [];
    this.saveHistory();
  }

  /**
   * 使用默认标签初始化历史记录
   */
  async initializeWithDefaults(defaultLabels: string[]): Promise<void> {
    // 不清空现有历史，只添加新的默认标签
    const existingLabels = new Set(this.history.map(item => item.label));
    
    defaultLabels.forEach(label => {
      if (!existingLabels.has(label) && label !== '*') {
        this.history.push({
          label,
          timestamp: Date.now(),
          frequency: 0 // 默认标签频率为0，用户使用后会增加
        });
      }
    });

    this.saveHistory();
  }

  /**
   * 搜索历史记录
   */
  searchHistory(query: string): string[] {
    const normalizedQuery = query.toLowerCase().trim();
    return this.history
      .filter(item => item.label.toLowerCase().includes(normalizedQuery))
      .sort((a, b) => {
        // 优先按频率排序
        if (b.frequency !== a.frequency) {
          return b.frequency - a.frequency;
        }
        // 频率相同则按时间排序
        return b.timestamp - a.timestamp;
      })
      .map(item => item.label);
  }
}

// 导出单例
export const SearchHistoryManager = new SearchHistoryManagerClass();
