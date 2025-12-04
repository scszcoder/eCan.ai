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

    // Sync active sheet's document to skillInfo.workFlow before saving
    // Note: skillInfo.workFlow should always reflect the main sheet's document for backend compatibility
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
      
      // Debug log to verify sheets data is being saved
      console.log('[AutoSave] Saving sheets:', {
        sheetCount: Object.keys(saveData.sheets.sheets).length,
        order: saveData.sheets.order,
        activeSheetId: saveData.sheets.activeSheetId,
        sheetsWithDocs: Object.entries(saveData.sheets.sheets).map(([id, s]) => ({
          id,
          name: (s as any).name,
          hasDoc: !!(s as any).document,
          nodeCount: (s as any).document?.nodes?.length ?? 0,
        })),
      });
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
  // Include all sheets data to detect new sheet creation and edits
  const fingerprint = React.useMemo(() => {
    const workFlow = skillInfo?.workFlow;
    const nodes = workFlow?.nodes?.map((n: any) => {
      const pos = `${n.meta?.position?.x ?? 0}:${n.meta?.position?.y ?? 0}`;
      const inputs = n.data?.inputsValues ? JSON.stringify(n.data.inputsValues) : '';
      return `${n.id}:${pos}:${inputs}`;
    }).join(',') ?? '';
    
    // Include sheets metadata AND document content to detect all changes
    const sheetsHash = Object.keys(sheets.sheets).sort().map(id => {
      const s = sheets.sheets[id];
      const doc = s.document;
      // Include node positions and data to detect content changes
      const nodesHash = doc?.nodes?.map((n: any) => {
        const pos = `${n.meta?.position?.x ?? 0}:${n.meta?.position?.y ?? 0}`;
        const data = n.data ? JSON.stringify(n.data).slice(0, 100) : '';
        return `${n.id}:${n.type}:${pos}:${data.length}`;
      }).join(',') ?? '';
      const edgesHash = doc?.edges?.map((e: any) => `${e.source}>${e.target}`).join(',') ?? '';
      return `${id}:${s.name}:${nodesHash}:${edgesHash}`;
    }).join(';');
    
    return `${skillInfo?.skillName}|${sheets.activeSheetId}|${sheets.order.join(',')}|${sheets.openTabs.join(',')}|${sheetsHash}|${breakpoints.length}|${currentFilePath}|${workFlow?.nodes?.length}|${workFlow?.edges?.length}|${nodes}`;
  }, [skillInfo?.skillName, skillInfo?.workFlow, sheets, breakpoints, currentFilePath]);

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
    }, 1500); // 1500ms debounce - must be > onContentChange debounce (1000ms) to ensure sheets are synced

    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, [fingerprint, autoSaveEnabled, saveToFile, currentFilePath]);
};
