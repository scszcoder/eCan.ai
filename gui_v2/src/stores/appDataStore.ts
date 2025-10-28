import { create } from 'zustand';
import { persist } from 'zustand/middleware';

/**
 * AppDataStore - 应用全局DataStorage
 *
 * All领域Data已Migration到专用的 domain stores：
 * - agents -> useAgentStore
 * - tasks -> useTaskStore
 * - skills -> useSkillStore
 * - vehicles -> useVehicleStore
 * - knowledges -> useKnowledgeStore
 * - chats -> useChatStore
 * - tools -> useToolStore
 * - settings -> useSettingsStore (专门的Settings管理)
 *
 * 此 store 仅保留：
 * - 全局Status（loading, error, initialized）
 */
export interface AppData {
  // 全局Status
  isLoading: boolean;
  error: string | null;
  initialized: boolean;

  // 全局Status管理
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setInitialized: (v: boolean) => void;
}

const useAppDataStore = create<AppData>()(
  persist(
    (set) => ({
      // 全局Status
      isLoading: false,
      error: null,
      initialized: false,

      // 全局Status管理
      setLoading: (loading) => set({ isLoading: loading }),
      setError: (error) => set({ error }),
      setInitialized: (v) => set({ initialized: v }),
    }),
    {
      name: 'app-data-storage',
    }
  )
);

export { useAppDataStore };