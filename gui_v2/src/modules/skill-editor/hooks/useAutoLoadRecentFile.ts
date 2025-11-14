/**
 * Auto-load Recent File Hook
 * Automatically loads the most recent file when the skill editor initializes
 */

import { useEffect, useRef } from 'react';
import { useClientContext } from '@flowgram.ai/free-layout-editor';
import { useSkillInfoStore } from '../stores/skill-info-store';
import { useRecentFilesStore } from '../stores/recent-files-store';
import { hasIPCSupport, hasFullFilePaths } from '../../../config/platform';
import { SkillInfo } from '../typings/skill-info';
import '../../../services/ipc/file-api'; // Import file API extensions

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
  const setCurrentFilePath = useSkillInfoStore((state) => state.setCurrentFilePath);
  const setHasUnsavedChanges = useSkillInfoStore((state) => state.setHasUnsavedChanges);
  const skillInfo = useSkillInfoStore((state) => state.skillInfo);
  const getMostRecentFile = useRecentFilesStore((state) => state.getMostRecentFile);
  
  const hasAutoLoaded = useRef(false);

  useEffect(() => {
    // Only auto-load once and if enabled
    if (!enabled || hasAutoLoaded.current || skillInfo) {
      return;
    }

    // Only auto-load if we have full file path support (desktop mode)
    if (!hasIPCSupport() || !hasFullFilePaths()) {
      return;
    }

    // Wait for workflow document to be available
    if (!workflowDocument) {
      return;
    }

    const autoLoadRecentFile = async () => {
      try {
        const mostRecentFile = getMostRecentFile();
        
        if (!mostRecentFile) {
          console.log('[AutoLoad] No recent files found');
          return;
        }

        console.log('[AutoLoad] Loading most recent file:', mostRecentFile.filePath);
        onAutoLoadStart?.();

        // Import IPC API dynamically
        const { IPCAPI } = await import('../../../services/ipc/api');
        const ipcApi = IPCAPI.getInstance();

        // Try to read the most recent file
        const fileResponse = await ipcApi.readSkillFile(mostRecentFile.filePath);

        if (fileResponse.success && fileResponse.data) {
          const data = JSON.parse(fileResponse.data.content) as SkillInfo;
          const diagram = data.workFlow;

          // Normalize skillName from folder when auto-loading
          // Expect path like: <...>/<name>_skill/diagram_dir/<name>_skill.json
          try {
            const norm = String(mostRecentFile.filePath).replace(/\\/g, '/');
            const parts = norm.split('/');
            const idx = parts.lastIndexOf('diagram_dir');
            if (idx > 0) {
              const folder = parts[idx - 1];
              const nameFromFolder = folder?.replace(/_skill$/i, '');
              if (nameFromFolder && data && typeof data === 'object') {
                if (!data.skillName || data.skillName !== nameFromFolder) {
                  (data as any).skillName = nameFromFolder;
                }
              }
            }
          } catch {}

          if (diagram) {
            // Set skill info with file path
            setSkillInfo(data);
            setCurrentFilePath(mostRecentFile.filePath);
            setHasUnsavedChanges(false);

            // Find and set breakpoints
            const breakpointIds = diagram.nodes
              .filter((node: any) => node.data?.break_point)
              .map((node: any) => node.id);
            setBreakpoints(breakpointIds);

            // Load diagram into the editor
            workflowDocument.clear();
            workflowDocument.fromJSON(diagram);
            workflowDocument.fitView && workflowDocument.fitView();

            console.log('[AutoLoad] Successfully loaded:', mostRecentFile.fileName);
            onAutoLoadSuccess?.(mostRecentFile.filePath, data);
          } else {
            // Fallback for older formats
            workflowDocument.clear();
            workflowDocument.fromJSON(data as any);
            workflowDocument.fitView && workflowDocument.fitView();

            setSkillInfo(data);
            setCurrentFilePath(mostRecentFile.filePath);
            setHasUnsavedChanges(false);

            console.log('[AutoLoad] Successfully loaded (legacy format):', mostRecentFile.fileName);
            onAutoLoadSuccess?.(mostRecentFile.filePath, data);
          }
        } else {
          console.warn('[AutoLoad] Failed to read file:', fileResponse.error);
          // File might have been moved or deleted, but don't treat as error
        }
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
    skillInfo,
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
  return useAutoLoadRecentFile({
    enabled: true,
    onAutoLoadStart: () => console.log('[AutoLoad] Starting auto-load...'),
    onAutoLoadSuccess: (filePath, skillInfo) => 
      console.log(`[AutoLoad] Successfully loaded: ${skillInfo.skillName || 'Untitled'} from ${filePath}`),
    onAutoLoadError: (error) => 
      console.error('[AutoLoad] Failed to auto-load recent file:', error.message),
  });
}
