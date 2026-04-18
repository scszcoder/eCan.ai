/**
 * Auto-load Recent File Hook
 * Automatically loads the most recent file when the skill editor initializes
 */

import { useEffect, useRef, useState } from 'react';
import { useClientContext } from '@flowgram.ai/free-layout-editor';
import { useSkillInfoStore } from '../stores/skill-info-store';
import { IPCAPI } from '../../../services/ipc/api';
import { useRecentFilesStore } from '../stores/recent-files-store';
import { useSheetsStore } from '../stores/sheets-store';
import { useNodeFlipStore } from '../stores/node-flip-store';
import { SkillInfo } from '../typings/skill-info';
import { loadSkillFile } from '../services/skill-loader';
import '../../../services/ipc/file-api'; // Import file API extensions
import { PageRefreshManager } from '../../../services/events/PageRefreshManager';

interface AutoLoadOptions {
  enabled?: boolean;
  startupDelayMs?: number;
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
    startupDelayMs = 600,
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
  
  const setIsSkillLoading = useSkillInfoStore((state) => state.setIsSkillLoading);

  const hasAutoLoaded = useRef(false);
  const [isAutoLoading, setIsAutoLoading] = useState(true);

  useEffect(() => {
    // Get IPC API instance once at the start
    const ipcApi = IPCAPI.getInstance();
    
    console.log('[AutoLoad][useEffect] Triggered with:', {
      enabled,
      hasAutoLoaded: hasAutoLoaded.current,
      currentFilePath,
      hasIPC: !!ipcApi,
      hasWorkflowDoc: !!workflowDocument,
    });

    // Only auto-load once and if enabled
    if (!enabled || hasAutoLoaded.current) {
      console.log('[AutoLoad] Skipped: enabled=', enabled, 'hasAutoLoaded=', hasAutoLoaded.current);
      setIsAutoLoading(false);
      return;
    }

    // Skip auto-load if a file is already loaded
    if (currentFilePath) {
      console.log('[AutoLoad] Skipped: file already loaded:', currentFilePath);
      hasAutoLoaded.current = true;
      setIsAutoLoading(false);
      return;
    }

    // Check if IPC API is available (more reliable than platform detection)
    // Platform detection might be unstable during early initialization
    if (!ipcApi) {
      console.log('[AutoLoad] Skipped: IPC API not available');
      setIsAutoLoading(false);
      return;
    }

    // Wait for workflow document to be available
    if (!workflowDocument) {
      console.log('[AutoLoad] Waiting for workflow document...');
      return;
    }

    console.log('[AutoLoad] ✅ Scheduling deferred auto-load process...');
    setIsAutoLoading(true);

    const autoLoadRecentFile = async () => {
      setIsSkillLoading(true);
      try {
        PageRefreshManager.consumeSkillEditorReload();
        
        // First, try to get recent files from backend (more reliable than localStorage)
        
        let fileToLoad: { filePath: string; fileName: string; timestamp?: number } | null = null;
        
        // Try to load recent files from backend
        try {
          console.log('[AutoLoad] Calling backend loadEditorCache...');
          const cacheResponse = await ipcApi.loadEditorCache<{ 
            cacheData: any; 
            recentFiles?: Array<{ filePath: string; fileName: string; skillName?: string; lastOpened?: string }> 
          }>();

          console.log('[AutoLoad] Backend response:', cacheResponse);
          const recentFiles = cacheResponse.success ? cacheResponse.data?.recentFiles : undefined;
          if (recentFiles && recentFiles.length > 0) {
            const mostRecent = recentFiles[0];
            console.log('[AutoLoad] Found most recent file from backend:', mostRecent);
            fileToLoad = {
              filePath: mostRecent.filePath,
              fileName: mostRecent.fileName,
              timestamp: mostRecent.lastOpened ? new Date(mostRecent.lastOpened).getTime() : Date.now(),
            };
          } else {
            console.log('[AutoLoad] No recent files from backend');
          }
        } catch (e) {
          console.error('[AutoLoad] Backend error:', e);
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

        // Use lightweight load first so the editor becomes interactive sooner.
        const result = await loadSkillFile(fileToLoad.filePath, {
          autoSaveMigrated: false,
          lightweight: true,
        });
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

            const hydrateLater = () => {
              void loadSkillFile(absoluteFilePath, { autoSaveMigrated: true }).then((fullResult) => {
                if (!fullResult.success || !fullResult.skillInfo) {
                  return;
                }

                const latestPath = useSkillInfoStore.getState().currentFilePath;
                if (latestPath && latestPath !== absoluteFilePath) {
                  return;
                }

                if (fullResult.bundle) {
                  const loadBundle = useSheetsStore.getState().loadBundle;
                  loadBundle(fullResult.bundle);
                }

                if (fullResult.dataMapping || fullResult.bundle || fullResult.migrated) {
                  setSkillInfo(fullResult.skillInfo);
                }
              }).catch((error) => {
                console.warn('[AutoLoad] Background hydration failed:', error);
              });
            };

            const requestIdle = (globalThis as unknown as Window & {
              requestIdleCallback?: (callback: IdleRequestCallback, options?: IdleRequestOptions) => number;
            }).requestIdleCallback;

            if (typeof requestIdle === 'function') {
              requestIdle(() => hydrateLater(), { timeout: 2000 });
            } else {
              setTimeout(hydrateLater, 300);
            }
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
        setIsAutoLoading(false);
        setIsSkillLoading(false);
        onAutoLoadComplete?.();
      }
    };

    let timeoutId: ReturnType<typeof setTimeout> | undefined;
    let idleCallbackId: number | undefined;
    let cancelled = false;

    const runAutoLoad = () => {
      if (cancelled) {
        return;
      }
      void autoLoadRecentFile();
    };

    const scheduleAutoLoad = () => {
      const requestIdle = (globalThis as unknown as Window & {
        requestIdleCallback?: (callback: IdleRequestCallback, options?: IdleRequestOptions) => number;
      }).requestIdleCallback;

      if (typeof requestIdle === 'function') {
        idleCallbackId = requestIdle(() => {
          runAutoLoad();
        }, { timeout: 1500 });
        return;
      }

      timeoutId = setTimeout(runAutoLoad, 0);
    };

    timeoutId = setTimeout(scheduleAutoLoad, startupDelayMs);

    return () => {
      cancelled = true;
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
      const cancelIdle = (globalThis as unknown as Window & {
        cancelIdleCallback?: (handle: number) => void;
      }).cancelIdleCallback;
      if (idleCallbackId !== undefined && typeof cancelIdle === 'function') {
        cancelIdle(idleCallbackId);
      }
    };
  }, [
    enabled,
    currentFilePath,
    workflowDocument,
    startupDelayMs,
    setSkillInfo,
    setIsSkillLoading,
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
    isAutoLoading,
  };
}

/**
 * Simple auto-load hook with default options
 */
export function useSimpleAutoLoad() {
  return useAutoLoadRecentFile({ enabled: true });
}
