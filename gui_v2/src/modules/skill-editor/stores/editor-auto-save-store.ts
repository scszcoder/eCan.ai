/**
 * Editor Auto-Save Store - Direct file persistence for skill editor
 * Saves skill files directly to disk, no intermediate cache layer
 */

import { create } from 'zustand';
import type { SkillInfo } from '../typings/skill-info';
import type { Sheet } from './sheets-store';
import { IPCAPI } from '../../../services/ipc/api';
import React from 'react';

// Data structure for saving to backend
export interface EditorSaveData {
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
  viewState: { zoom?: number } | null;
  selectionIds: string[];
}

interface AutoSaveState {
  autoSaveEnabled: boolean;
  setAutoSaveEnabled: (enabled: boolean) => void;
  saveToFile: (data: EditorSaveData) => Promise<boolean>;
}

export const useAutoSaveStore = create<AutoSaveState>()((set, get) => ({
  // Auto-save is enabled by default; can be toggled by hooks like useAutoLoadRecentFile if needed
  autoSaveEnabled: true,

  setAutoSaveEnabled: (enabled: boolean) => {
    set({ autoSaveEnabled: enabled });
  },

  saveToFile: async (data: EditorSaveData) => {
    const state = get();
    if (!state.autoSaveEnabled) {
      return false;
    }

    // Sync sheets.main.document to skillInfo.workFlow before saving
    let saveData = { ...data };
    if (saveData.skillInfo && saveData.sheets?.sheets) {
      const mainSheetId = saveData.sheets.order?.[0] || 'main';
      const mainSheet = saveData.sheets.sheets[mainSheetId];
      if (mainSheet?.document) {
        saveData.skillInfo = {
          ...saveData.skillInfo,
          workFlow: mainSheet.document,
          lastModified: new Date().toISOString(),
        };
      }
    }

    try {
      const ipcApi = IPCAPI.getInstance();
      const response = await ipcApi.saveEditorCache({
        version: '1.0.0',
        ...saveData,
      });
      
      return response.success;
    } catch (e) {
      console.error('[AutoSave] Error:', e);
      return false;
    }
  },
}));

/**
 * Hook to auto-save editor state to file
 * Uses fingerprinting to detect actual content changes, avoiding unnecessary saves
 */
export const useAutoSave = (
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
  const saveToFile = useAutoSaveStore((state) => state.saveToFile);
  const autoSaveEnabled = useAutoSaveStore((state) => state.autoSaveEnabled);
  
  const lastSavedHashRef = React.useRef<string>('');
  const timeoutRef = React.useRef<NodeJS.Timeout | null>(null);
  
  // Use refs to get latest values in setTimeout callback
  const skillInfoRef = React.useRef(skillInfo);
  const sheetsRef = React.useRef(sheets);
  const breakpointsRef = React.useRef(breakpoints);
  const currentFilePathRef = React.useRef(currentFilePath);
  const viewStateRef = React.useRef(viewState);
  const selectionIdsRef = React.useRef(selectionIds);
  
  // Update refs on every render
  skillInfoRef.current = skillInfo;
  sheetsRef.current = sheets;
  breakpointsRef.current = breakpoints;
  currentFilePathRef.current = currentFilePath;
  viewStateRef.current = viewState;
  selectionIdsRef.current = selectionIds;

  // Create a fingerprint to detect changes
  // Use skillInfo.workFlow as primary source since onContentChange updates it directly
  const fingerprint = React.useMemo(() => {
    const workFlow = skillInfo?.workFlow;
    const nodes = workFlow?.nodes?.map((n: any) => {
      const pos = `${n.meta?.position?.x ?? 0}:${n.meta?.position?.y ?? 0}`;
      const inputs = n.data?.inputsValues ? JSON.stringify(n.data.inputsValues) : '';
      return `${n.id}:${pos}:${inputs}`;
    }).join(',') ?? '';
    
    return `${skillInfo?.skillName}|${sheets.activeSheetId}|${breakpoints.length}|${currentFilePath}|${workFlow?.nodes?.length}|${workFlow?.edges?.length}|${nodes}`;
  }, [skillInfo?.skillName, skillInfo?.workFlow, sheets.activeSheetId, breakpoints, currentFilePath]);

  // Auto-save when content changes
  React.useEffect(() => {
    // Only save if we have a file path (skip for new unsaved skills)
    if (!autoSaveEnabled || !currentFilePath) {
      return;
    }

    if (fingerprint === lastSavedHashRef.current) {
      return;
    }

    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }

    timeoutRef.current = setTimeout(() => {
      if (fingerprint !== lastSavedHashRef.current) {
        lastSavedHashRef.current = fingerprint;
        // Use refs to get latest values
        saveToFile({
          timestamp: Date.now(),
          skillInfo: skillInfoRef.current,
          sheets: sheetsRef.current,
          breakpoints: breakpointsRef.current,
          currentFilePath: currentFilePathRef.current,
          viewState: viewStateRef.current,
          selectionIds: selectionIdsRef.current,
        });
      }
    }, 500); // 500ms debounce after state settles

    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, [fingerprint, autoSaveEnabled, saveToFile, currentFilePath]);
};
