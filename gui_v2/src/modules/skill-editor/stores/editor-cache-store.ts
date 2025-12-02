/**
 * Editor Cache Store - Real-time persistence for skill editor
 * Saves all editor content to Python backend and restores on page load/refresh
 */

import { create } from 'zustand';
import type { SkillInfo } from '../typings/skill-info';
import type { Sheet } from './sheets-store';
import { IPCAPI } from '../../../services/ipc/api';

const CACHE_VERSION = '1.0.0';

export interface EditorCacheData {
  version: string;
  timestamp: number;
  skillInfo: SkillInfo | null;
  sheets: {
    sheets: Record<string, Sheet>;
    order: string[];
    openTabs: string[];
    activeSheetId: string | null;
  };
  breakpoints: string[];
  currentFilePath: string | null;
  viewState: {
    zoom?: number;
  } | null;
  selectionIds: string[];
}

interface EditorCacheState {
  // Cache data
  cachedData: EditorCacheData | null;
  
  // Actions
  saveCache: (data: Partial<EditorCacheData>) => Promise<void>;
  loadCache: () => Promise<EditorCacheData | null>;
  clearCache: () => Promise<void>;
  hasCachedData: () => boolean;
  
  // Auto-save control
  autoSaveEnabled: boolean;
  setAutoSaveEnabled: (enabled: boolean) => void;
}

const createEmptyCacheData = (): EditorCacheData => ({
  version: CACHE_VERSION,
  timestamp: Date.now(),
  skillInfo: null,
  sheets: {
    sheets: {},
    order: [],
    openTabs: [],
    activeSheetId: null,
  },
  breakpoints: [],
  currentFilePath: null,
  viewState: null,
  selectionIds: [],
});

export const useEditorCacheStore = create<EditorCacheState>()((set, get) => ({
  cachedData: null,
  autoSaveEnabled: true,

      saveCache: async (data: Partial<EditorCacheData>) => {
        const state = get();
        if (!state.autoSaveEnabled) {
          console.log('[EditorCache] Auto-save disabled, skipping cache update');
          return;
        }

        const currentCache = state.cachedData || createEmptyCacheData();
        const updatedCache: EditorCacheData = {
          ...currentCache,
          ...data,
          version: CACHE_VERSION,
          timestamp: Date.now(),
        };

        set({ cachedData: updatedCache });
        console.log('[EditorCache] Cache saved to memory:', {
          timestamp: new Date(updatedCache.timestamp).toLocaleString(),
          hasSkillInfo: !!updatedCache.skillInfo,
          sheetsCount: Object.keys(updatedCache.sheets.sheets).length,
          openTabsCount: updatedCache.sheets.openTabs.length,
        });
        
        // Save to Python backend for persistent storage
        try {
          const ipcApi = IPCAPI.getInstance();
          const response = await ipcApi.saveEditorCache(updatedCache);
          if (response.success) {
            console.log('[EditorCache] Cache persisted to backend:', response.data);
          } else {
            console.error('[EditorCache] Failed to persist to backend:', response.error);
          }
        } catch (e) {
          console.error('[EditorCache] Error persisting to backend:', e);
        }
      },

      loadCache: async () => {
        // Load from Python backend
        try {
          const ipcApi = IPCAPI.getInstance();
          const response = await ipcApi.loadEditorCache<{ cacheData: EditorCacheData | null; filePath?: string }>();
          
          if (!response.success) {
            console.error('[EditorCache] Failed to load from backend:', response.error);
            return null;
          }

          const cached = response.data?.cacheData;
          
          if (!cached) {
            console.log('[EditorCache] No cached data found in backend');
            return null;
          }

          // Version check
          if (cached.version !== CACHE_VERSION) {
            console.warn('[EditorCache] Cache version mismatch, clearing cache', {
              cached: cached.version,
              current: CACHE_VERSION,
            });
            await ipcApi.clearEditorCache();
            return null;
          }

          console.log('[EditorCache] Cache loaded from backend:', {
            timestamp: new Date(cached.timestamp).toLocaleString(),
            hasSkillInfo: !!cached.skillInfo,
            sheetsCount: Object.keys(cached.sheets.sheets).length,
            openTabsCount: cached.sheets.openTabs.length,
            filePath: response.data?.filePath,
          });

          // Update store with loaded data
          set({ cachedData: cached });
          return cached;
        } catch (error) {
          console.error('[EditorCache] Error loading cache from backend:', error);
          return null;
        }
      },

      clearCache: async () => {
        set({ cachedData: null });
        console.log('[EditorCache] Cache cleared from memory');
        
        // Clear from Python backend
        try {
          const ipcApi = IPCAPI.getInstance();
          const response = await ipcApi.clearEditorCache();
          if (response.success) {
            console.log('[EditorCache] Cache cleared from backend');
          } else {
            console.error('[EditorCache] Failed to clear backend cache:', response.error);
          }
        } catch (e) {
          console.error('[EditorCache] Error clearing backend cache:', e);
        }
      },

      hasCachedData: () => {
        const state = get();
        return state.cachedData !== null;
      },

  setAutoSaveEnabled: (enabled: boolean) => {
    set({ autoSaveEnabled: enabled });
    console.log('[EditorCache] Auto-save', enabled ? 'enabled' : 'disabled');
  },
}));

// Import React for useEffect and useRef
import React from 'react';

/**
 * Hook to auto-save editor state to cache
 * Uses JSON serialization to detect actual content changes, avoiding unnecessary saves
 */
export const useAutoSaveCache = (
  skillInfo: SkillInfo | null,
  sheets: {
    sheets: Record<string, Sheet>;
    order: string[];
    openTabs: string[];
    activeSheetId: string | null;
  },
  breakpoints: string[],
  currentFilePath: string | null,
  viewState: { zoom?: number } | null,
  selectionIds: string[]
) => {
  const saveCache = useEditorCacheStore((state) => state.saveCache);
  const autoSaveEnabled = useEditorCacheStore((state) => state.autoSaveEnabled);
  
  // Track last saved content hash to avoid duplicate saves
  const lastSavedHashRef = React.useRef<string>('');
  const timeoutRef = React.useRef<NodeJS.Timeout | null>(null);

  // Create a revision counter based on sheets changes
  // This is more reliable than hashing the entire content
  const sheetsRevision = React.useMemo(() => {
    // Create a fingerprint that includes node positions to detect moves
    const fingerprint = Object.entries(sheets.sheets).map(([id, sheet]) => {
      const doc = sheet.document;
      // Include node positions in fingerprint to detect moves
      const nodePositions = doc?.nodes?.map((n: any) => 
        `${n.id}:${n.meta?.position?.x ?? 0}:${n.meta?.position?.y ?? 0}`
      ).join(',') ?? '';
      return `${id}:${doc?.nodes?.length ?? 0}:${doc?.edges?.length ?? 0}:${nodePositions}`;
    }).join('|');
    return `${skillInfo?.skillName}|${sheets.activeSheetId}|${breakpoints.length}|${currentFilePath}|${fingerprint}`;
  }, [skillInfo?.skillName, sheets.sheets, sheets.activeSheetId, breakpoints, currentFilePath]);

  // Auto-save only when content actually changes
  React.useEffect(() => {
    if (!autoSaveEnabled) return;
    
    // Skip if content hasn't changed
    if (sheetsRevision === lastSavedHashRef.current) {
      return;
    }

    // Clear any pending save
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }

    timeoutRef.current = setTimeout(() => {
      // Double-check revision hasn't been saved by another effect
      if (sheetsRevision !== lastSavedHashRef.current) {
        lastSavedHashRef.current = sheetsRevision;
        saveCache({
          skillInfo,
          sheets,
          breakpoints,
          currentFilePath,
          viewState,
          selectionIds,
        });
      }
    }, 500); // Debounce 500ms

    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, [sheetsRevision, autoSaveEnabled, saveCache, skillInfo, sheets, breakpoints, currentFilePath, viewState, selectionIds]);
};
