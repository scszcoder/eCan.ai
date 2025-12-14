/**
 * Auto-load Recent File Hook
 * Automatically loads the most recent file when the skill editor initializes
 */

import { useEffect, useRef } from 'react';
import { useClientContext } from '@flowgram.ai/free-layout-editor';
import { useSkillInfoStore } from '../stores/skill-info-store';
import { useRecentFilesStore } from '../stores/recent-files-store';
import { useSheetsStore } from '../stores/sheets-store';
import { useNodeFlipStore } from '../stores/node-flip-store';
import { SkillInfo } from '../typings/skill-info';
import { loadSkillFile } from '../services/skill-loader';
import '../../../services/ipc/file-api'; // Import file API extensions
import { PageRefreshManager } from '../../../services/events/PageRefreshManager';

interface AutoLoadOptions {
  enabled?: boolean;
  onAutoLoadStart?: () => void;
  onAutoLoadSuccess?: (filePath: string, skillInfo: SkillInfo) => void;
  onAutoLoadError?: (error: Error) => void;
  onAutoLoadComplete?: () => void;
}

/**
 * Hook to automatically load the most recent file on skill editor startup
 */
export function useAutoLoadRecentFile(options: AutoLoadOptions = {}) {
  const {
    enabled = true,
    onAutoLoadStart,
    onAutoLoadSuccess,
    onAutoLoadError,
    onAutoLoadComplete,
  } = options;

  const clientContext = useClientContext();
  const workflowDocument = clientContext?.document;
  const setSkillInfo = useSkillInfoStore((state) => state.setSkillInfo);
  const setBreakpoints = useSkillInfoStore((state) => state.setBreakpoints);
  const currentFilePath = useSkillInfoStore((state) => state.currentFilePath);
  const setCurrentFilePath = useSkillInfoStore((state) => state.setCurrentFilePath);
  const setHasUnsavedChanges = useSkillInfoStore((state) => state.setHasUnsavedChanges);
  const getMostRecentFile = useRecentFilesStore((state) => state.getMostRecentFile);
  
  const hasAutoLoaded = useRef(false);

  useEffect(() => {
    // Only auto-load once and if enabled
    if (!enabled || hasAutoLoaded.current) {
      return;
    }

    // Skip auto-load if a file is already loaded
    if (currentFilePath) {
      hasAutoLoaded.current = true;
      return;
    }

    // Only auto-load if we have IPC support (desktop mode)
    const hasIPC = typeof window !== 'undefined' && !!(window as any).ipc;
    if (!hasIPC) {
      return;
    }

    // Wait for workflow document to be available
    if (!workflowDocument) {
      return;
    }

    const autoLoadRecentFile = async () => {
      try {
        PageRefreshManager.consumeSkillEditorReload();
        
        // First, try to get recent files from backend (more reliable than localStorage)
        const { IPCAPI } = await import('../../../services/ipc/api');
        const ipcApi = IPCAPI.getInstance();
        
        let fileToLoad: { filePath: string; fileName: string; timestamp?: number } | null = null;
        
        // Try to load recent files from backend
        try {
          const cacheResponse = await ipcApi.loadEditorCache<{ 
            cacheData: any; 
            recentFiles?: Array<{ filePath: string; fileName: string; skillName?: string; lastOpened?: string }> 
          }>();

          const recentFiles = cacheResponse.success ? cacheResponse.data?.recentFiles : undefined;
          if (recentFiles && recentFiles.length > 0) {
            const mostRecent = recentFiles[0];
            fileToLoad = {
              filePath: mostRecent.filePath,
              fileName: mostRecent.fileName,
              timestamp: mostRecent.lastOpened ? new Date(mostRecent.lastOpened).getTime() : Date.now(),
            };
          }
        } catch (e) {
          // Backend might not have recent files yet
        }
        
        // Fallback to localStorage if backend has no recent files
        if (!fileToLoad) {
          fileToLoad = getMostRecentFile();
        }
        
        // If no recent files, try to load default demo0 skill
        if (!fileToLoad) {
          const demo0Path = 'my_skills/demo0_skill/diagram_dir/demo0_skill.json';
          try {
            const checkResponse = await ipcApi.readSkillFile(demo0Path);
            if (checkResponse.success && checkResponse.data) {
              fileToLoad = {
                filePath: demo0Path,
                fileName: 'demo0_skill.json',
                timestamp: Date.now(),
              };
            } else {
              // No demo0, use initial-data.ts (default)
              hasAutoLoaded.current = true;
              return;
            }
          } catch (e) {
            // Error loading demo0, use initial-data.ts (default)
            hasAutoLoaded.current = true;
            return;
          }
        }

        onAutoLoadStart?.();

        // Use unified skill loader (handles migration automatically)
        const result = await loadSkillFile(fileToLoad.filePath);
        const absoluteFilePath = result.filePath;

        if (result.success && result.skillInfo) {
          const data = result.skillInfo;
          const diagram = data.workFlow;
          // skillName is already normalized by skill-loader.ts

          if (diagram) {
            // Set skill info with file path
            setSkillInfo(data);
            setCurrentFilePath(absoluteFilePath);
            setHasUnsavedChanges(false);

            // Find and set breakpoints
            const breakpointIds = diagram.nodes
              .filter((node: any) => node.data?.break_point)
              .map((node: any) => node.id);
            setBreakpoints(breakpointIds);

            // Load bundle if available, otherwise load single skill
            if (result.bundle) {
              const loadBundle = useSheetsStore.getState().loadBundle;
              loadBundle(result.bundle);
            } else {
              // Load diagram into the editor
              workflowDocument.clear();
              workflowDocument.fromJSON(diagram);
              
              // Fallback: update sheets store with loaded document if no bundle
              const saveActiveDocument = useSheetsStore.getState().saveActiveDocument;
              if (saveActiveDocument) {
                saveActiveDocument(diagram);
              }
            }
            
            // Restore flip states from saved node data
            const { setFlipped, clear: clearFlipStore } = useNodeFlipStore.getState();
            clearFlipStore();
            
            setTimeout(() => {
              diagram.nodes.forEach((node: any) => {
                if (node?.data?.hFlip === true) {
                  console.log('[AutoLoad] Restoring hFlip state for node:', node.id);
                  setFlipped(node.id, true);
                }
              });
            }, 100);
            
            workflowDocument.fitView && workflowDocument.fitView();

            onAutoLoadSuccess?.(absoluteFilePath, data);
          } else {
            // Fallback for older formats
            workflowDocument.clear();
            workflowDocument.fromJSON(data as any);
            
            // Restore flip states for older formats
            const { setFlipped, clear: clearFlipStore } = useNodeFlipStore.getState();
            clearFlipStore();
            if ((data as any).nodes) {
              setTimeout(() => {
                (data as any).nodes.forEach((node: any) => {
                  if (node?.data?.hFlip === true) {
                    console.log('[AutoLoad] Restoring hFlip state for node (fallback):', node.id);
                    setFlipped(node.id, true);
                  }
                });
              }, 100);
            }
            
            workflowDocument.fitView && workflowDocument.fitView();

            setSkillInfo(data);
            setCurrentFilePath(absoluteFilePath);
            setHasUnsavedChanges(false);

            // Also update sheets store
            const saveActiveDocument = useSheetsStore.getState().saveActiveDocument;
            if (saveActiveDocument) {
              saveActiveDocument(data as any);
            }

            onAutoLoadSuccess?.(absoluteFilePath, data);
          }
        }
        // If file read failed, just continue with default data
      } catch (error) {
        console.error('[AutoLoad] Error loading recent file:', error);
        onAutoLoadError?.(error as Error);
      } finally {
        hasAutoLoaded.current = true;
        onAutoLoadComplete?.();
      }
    };

    // Small delay to ensure the editor is fully initialized
    const timeoutId = setTimeout(autoLoadRecentFile, 100);

    return () => {
      clearTimeout(timeoutId);
    };
  }, [
    enabled,
    currentFilePath,
    workflowDocument,
    setSkillInfo,
    setBreakpoints,
    setCurrentFilePath,
    setHasUnsavedChanges,
    getMostRecentFile,
    onAutoLoadStart,
    onAutoLoadSuccess,
    onAutoLoadError,
    onAutoLoadComplete,
  ]);

  return {
    hasAutoLoaded: hasAutoLoaded.current,
  };
}

/**
 * Simple auto-load hook with default options
 */
export function useSimpleAutoLoad() {
  return useAutoLoadRecentFile({ enabled: true });
}
