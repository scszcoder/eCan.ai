/**
 * Skill History Store
 * Manages skill version history state for the editor
 */

import { create } from 'zustand';
import { IPCAPI } from '../../../services/ipc/api';
import { SkillHistoryRecord, SkillHistoryListResponse, RestoreResult } from '../types/skill-history';

interface SkillHistoryState {
  // State
  historyList: SkillHistoryRecord[];
  totalCount: number;
  maxHistory: number;
  currentPage: number;
  pageSize: number;
  isLoading: boolean;
  error: string | null;
  selectedHistoryId: string | null;

  // Actions
  fetchHistoryList: (skillId: string) => Promise<void>;
  loadMore: (skillId: string) => Promise<void>;
  selectHistory: (historyId: string | null) => void;
  restoreFromHistory: (historyId: string) => Promise<RestoreResult | null>;
  deleteHistory: (historyId: string) => Promise<boolean>;
  deleteAllHistory: (skillId: string) => Promise<boolean>;
  clearError: () => void;
  reset: () => void;
}

const DEFAULT_PAGE_SIZE = 20;

export const useSkillHistoryStore = create<SkillHistoryState>((set, get) => ({
  // Initial state
  historyList: [],
  totalCount: 0,
  maxHistory: 100,
  currentPage: 0,
  pageSize: DEFAULT_PAGE_SIZE,
  isLoading: false,
  error: null,
  selectedHistoryId: null,

  // Actions
  fetchHistoryList: async (skillId: string) => {
    if (!skillId) return;

    set({ isLoading: true, error: null });
    try {
      const api = IPCAPI.getInstance();
      const response = await api.getSkillHistoryList<SkillHistoryListResponse>(skillId, DEFAULT_PAGE_SIZE, 0);

      if (response.success && response.data) {
        set({
          historyList: response.data.history_list || [],
          totalCount: response.data.total || 0,
          maxHistory: response.data.max_history || 100,
          currentPage: 0,
          isLoading: false,
        });
      } else {
        set({
          error: response.error?.message || 'Failed to fetch history list',
          isLoading: false,
        });
      }
    } catch (error: any) {
      set({
        error: error.message || 'Failed to fetch history list',
        isLoading: false,
      });
    }
  },

  loadMore: async (skillId: string) => {
    if (!skillId) return;

    const { currentPage, pageSize, historyList, isLoading } = get();
    if (isLoading) return;

    const nextPage = currentPage + 1;
    const offset = nextPage * pageSize;

    set({ isLoading: true });
    try {
      const api = IPCAPI.getInstance();
      const response = await api.getSkillHistoryList<SkillHistoryListResponse>(skillId, pageSize, offset);

      if (response.success && response.data) {
        set({
          historyList: [...historyList, ...(response.data.history_list || [])],
          currentPage: nextPage,
          isLoading: false,
        });
      } else {
        set({
          error: response.error?.message || 'Failed to load more history',
          isLoading: false,
        });
      }
    } catch (error: any) {
      set({
        error: error.message || 'Failed to load more history',
        isLoading: false,
      });
    }
  },

  selectHistory: (historyId: string | null) => {
    set({ selectedHistoryId: historyId });
  },

  restoreFromHistory: async (historyId: string) => {
    if (!historyId) return null;

    set({ isLoading: true, error: null });
    try {
      const api = IPCAPI.getInstance();
      const response = await api.restoreSkillFromHistory<RestoreResult>(historyId);

      if (response.success && response.data) {
        set({ isLoading: false });
        return response.data;
      } else {
        set({
          error: response.error?.message || 'Failed to restore from history',
          isLoading: false,
        });
        return null;
      }
    } catch (error: any) {
      set({
        error: error.message || 'Failed to restore from history',
        isLoading: false,
      });
      return null;
    }
  },

  deleteHistory: async (historyId: string) => {
    if (!historyId) return false;

    try {
      const api = IPCAPI.getInstance();
      const response = await api.deleteSkillHistory(historyId);

      if (response.success) {
        // Remove from local state
        const { historyList } = get();
        set({
          historyList: historyList.filter((h) => h.id !== historyId),
          totalCount: Math.max(0, get().totalCount - 1),
        });
        return true;
      } else {
        set({ error: response.error?.message || 'Failed to delete history' });
        return false;
      }
    } catch (error: any) {
      set({ error: error.message || 'Failed to delete history' });
      return false;
    }
  },

  deleteAllHistory: async (skillId: string) => {
    if (!skillId) return false;

    set({ isLoading: true, error: null });
    try {
      const api = IPCAPI.getInstance();
      const response = await api.deleteAllSkillHistory(skillId);

      if (response.success) {
        set({
          historyList: [],
          totalCount: 0,
          isLoading: false,
        });
        return true;
      } else {
        set({
          error: response.error?.message || 'Failed to delete all history',
          isLoading: false,
        });
        return false;
      }
    } catch (error: any) {
      set({
        error: error.message || 'Failed to delete all history',
        isLoading: false,
      });
      return false;
    }
  },

  clearError: () => {
    set({ error: null });
  },

  reset: () => {
    set({
      historyList: [],
      totalCount: 0,
      maxHistory: 100,
      currentPage: 0,
      pageSize: DEFAULT_PAGE_SIZE,
      isLoading: false,
      error: null,
      selectedHistoryId: null,
    });
  },
}));
