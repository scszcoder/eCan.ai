/**
 * Rank Store
 * Rank/Level data management store
 * 
 * Note: This file was previously incorrectly named taskStore.ts
 * Now correctly separated:
 * - rankStore.ts: Manages rank/level data
 * - taskStore.ts: Manages task data
 */

import { create } from 'zustand';

interface RankState {
  rankname: string | null;
  setRankname: (rankname: string) => void;
}

/**
 * Rank Store
 * 
 * Used to store the currently selected rank/level name
 * This is a simple state management store that doesn't require persistence or complex CRUD operations
 * 
 * @example
 * ```typescript
 * const { rankname, setRankname } = useRankStore();
 * 
 * // Set rank
 * setRankname('Senior');
 * ```
 */
export const useRankStore = create<RankState>((set) => ({
  rankname: null,
  setRankname: (rankname) => set({ rankname }),
}));

