import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { Settings } from '@/pages/Settings/types';
import appData from './app_data.json';

/**
 * AppDataStore - 应用全局数据存储
 *
 * 所有领域数据已迁移到专用的 domain stores：
 * - agents -> useAgentStore
 * - tasks -> useTaskStore
 * - skills -> useSkillStore
 * - vehicles -> useVehicleStore
 * - knowledges -> useKnowledgeStore
 * - chats -> useChatStore
 * - tools -> useToolStore
 *
 * 此 store 仅保留：
 * - settings（全局应用设置）
 * - 全局状态（loading, error, initialized）
 */
export interface AppData {
  // 全局应用设置
  settings: Settings | null;

  // 全局状态
  isLoading: boolean;
  error: string | null;
  initialized: boolean;

  // 全局状态管理
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setInitialized: (v: boolean) => void;

  // 设置管理
  setSettings: (settings: Settings) => void;
}

const useAppDataStore = create<AppData>()(
  persist(
    (set) => ({
      // 全局应用设置
      settings: appData.settings as any as Settings,

      // 全局状态
      isLoading: false,
      error: null,
      initialized: false,

      // 全局状态管理
      setLoading: (loading) => set({ isLoading: loading }),
      setError: (error) => set({ error }),
      setInitialized: (v) => set({ initialized: v }),

      // 设置管理
      setSettings: (settings) => set({ settings }),
    }),
    {
      name: 'app-data-storage',
    }
  )
);

export { useAppDataStore };