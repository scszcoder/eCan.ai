/**
 * Rank Store
 * 等级/职级数据管理 Store
 * 
 * 注意：这个文件之前错误地命名为 taskStore.ts
 * 现在已经正确分离：
 * - rankStore.ts: 管理等级/职级数据
 * - taskStore.ts: 管理任务数据
 */

import { create } from 'zustand';

interface RankState {
  rankname: string | null;
  setRankname: (rankname: string) => void;
}

/**
 * Rank Store
 * 
 * 用于存储当前选中的等级/职级名称
 * 这是一个简单的状态管理 store，不需要持久化或复杂的 CRUD 操作
 * 
 * @example
 * ```typescript
 * const { rankname, setRankname } = useRankStore();
 * 
 * // 设置等级
 * setRankname('Senior');
 * ```
 */
export const useRankStore = create<RankState>((set) => ({
  rankname: null,
  setRankname: (rankname) => set({ rankname }),
}));

