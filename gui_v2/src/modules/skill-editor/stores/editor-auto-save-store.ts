/**
 * Editor Auto-Save Store - Direct file persistence for skill editor
 * Saves skill files directly to disk, no intermediate cache layer
 */

import { create } from 'zustand';
import type { SkillInfo } from '../typings/skill-info';
import type { Sheet } from './sheets-store';
import { IPCAPI } from '../../../services/ipc/api';
import React from 'react';
import { useNodeFlipStore } from './node-flip-store';
import { sanitizeNodeApiKeys } from '../utils/sanitize-utils';

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

    // IMPORTANT: Read latest sheets directly from store to get the most recent document
    // (the data.sheets passed in may be stale due to React's batching)
    const { useSheetsStore } = await import('./sheets-store');
    const latestSheets = useSheetsStore.getState();
    
    // Sync active sheet's document to skillInfo.workFlow before saving
    // Note: skillInfo.workFlow should always reflect the main sheet's document for backend compatibility
    let saveData = { ...data };
    
    // Use latest sheets from store
    const sheetsToSave = {
      sheets: latestSheets.sheets,
      order: latestSheets.order,
      openTabs: latestSheets.openTabs,
      activeSheetId: latestSheets.activeSheetId,
    };
    saveData.sheets = sheetsToSave;
    
    if (saveData.skillInfo && sheetsToSave.sheets) {
      const mainSheetId = sheetsToSave.order?.[0] || 'main';
      const mainSheet = sheetsToSave.sheets[mainSheetId];
      if (mainSheet?.document) {
        saveData.skillInfo = {
          ...saveData.skillInfo,
          workFlow: mainSheet.document,
          lastModified: new Date().toISOString(),
        };
      }
      
    }

    try {
      // Deep clone for sanitization to avoid mutating store state
      const sanitizedData = JSON.parse(JSON.stringify(saveData));
      
      // Sanitize API keys in main workflow
      if (sanitizedData.skillInfo?.workFlow?.nodes) {
        sanitizeNodeApiKeys(sanitizedData.skillInfo.workFlow.nodes);
      }
      
      // Sanitize API keys in all sheets
      if (sanitizedData.sheets?.sheets) {
        Object.values(sanitizedData.sheets.sheets).forEach((sheet: any) => {
          if (sheet.document?.nodes) {
            sanitizeNodeApiKeys(sheet.document.nodes);
          }
        });
      }

      const ipcApi = IPCAPI.getInstance();
      const response = await ipcApi.saveEditorCache({
        version: '1.0.0',
        ...sanitizedData,
      });
      
      // If skill was renamed, update currentFilePath in store
      if (response.success && response.data) {
        const responseData = response.data as any;
        if (responseData.renamed && responseData.newFilePath) {
          console.log('[AutoSave] Skill renamed, updating path:', responseData.newFilePath);
          const { useSkillInfoStore } = await import('./skill-info-store');
          useSkillInfoStore.getState().setCurrentFilePath(responseData.newFilePath);
        }
      }
      
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
  // Also include NodeFlipStore version to detect flip changes
  const flipVersion = useNodeFlipStore((state) => state.version);
  
  const fingerprint = React.useMemo(() => {
    const workFlow = skillInfo?.workFlow;
    // Make fingerprint sensitive to node data (including hFlip) so flip changes trigger auto-save
    const nodes = workFlow?.nodes?.map((n: any) => {
      const pos = `${n.meta?.position?.x ?? 0}:${n.meta?.position?.y ?? 0}`;
      const inputs = n.data?.inputsValues ? JSON.stringify(n.data.inputsValues) : '';
      const dataSnippet = n.data ? JSON.stringify(n.data).slice(0, 120) : '';
      return `${n.id}:${pos}:${inputs}:${dataSnippet}`;
    }).join(',') ?? '';

    // Include sheets metadata AND document content to detect all changes
    const sheetsHash = Object.keys(sheets.sheets).sort().map(id => {
      const s = sheets.sheets[id];
      const doc = s.document;
      // Include node positions and data to detect content changes (not just length)
      const nodesHash = doc?.nodes?.map((n: any) => {
        const pos = `${n.meta?.position?.x ?? 0}:${n.meta?.position?.y ?? 0}`;
        const dataSnippet = n.data ? JSON.stringify(n.data).slice(0, 120) : '';
        return `${n.id}:${n.type}:${pos}:${dataSnippet}`;
      }).join(',') ?? '';
      const edgesHash = doc?.edges?.map((e: any) => `${e.source}>${e.target}`).join(',') ?? '';
      return `${id}:${s.name}:${nodesHash}:${edgesHash}`;
    }).join(';');

    // Include flipVersion to ensure fingerprint changes when any node is flipped
    return `${skillInfo?.skillName}|${sheets.activeSheetId}|${sheets.order.join(',')}|${sheets.openTabs.join(',')}|${sheetsHash}|${breakpoints.length}|${currentFilePath}|${workFlow?.nodes?.length}|${workFlow?.edges?.length}|${nodes}|flip:${flipVersion}`;
  }, [skillInfo?.skillName, skillInfo?.workFlow, sheets, breakpoints, currentFilePath, flipVersion]);

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
