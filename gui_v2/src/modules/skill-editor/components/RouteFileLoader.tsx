/**
 * Route File Loader Component
 * Loads a file from route state inside the FreeLayoutEditorProvider context
 */

import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { useClientContext } from '@flowgram.ai/free-layout-editor';
import { useSkillInfoStore } from '../stores/skill-info-store';
import { SkillInfo } from '../typings/skill-info';
import '../../../services/ipc/file-api';

export const RouteFileLoader = () => {
  const location = useLocation();
  const { document: workflowDocument } = useClientContext();
  const setSkillInfo = useSkillInfoStore((state) => state.setSkillInfo);
  const setBreakpoints = useSkillInfoStore((state) => state.setBreakpoints);
  const setCurrentFilePath = useSkillInfoStore((state) => state.setCurrentFilePath);
  const setHasUnsavedChanges = useSkillInfoStore((state) => state.setHasUnsavedChanges);
  
  const lastLoadedPath = useRef<string | null>(null);
  const lastLocationKey = useRef<string | null>(null);

  useEffect(() => {
    // Check if we have a file path in route state
    const state = location.state as { filePath?: string; skillId?: string } | null;
    const locationKey = location.key || 'default';
    
    console.log('[RouteFileLoader] Effect triggered:', {
      hasState: !!state,
      filePath: state?.filePath,
      lastLoadedPath: lastLoadedPath.current,
      locationKey,
      lastLocationKey: lastLocationKey.current
    });
    
    if (!state?.filePath) {
      return;
    }

    // Skip if already loaded this exact path with same location key
    // (location.key changes on each navigation, even to same path)
    if (lastLoadedPath.current === state.filePath && lastLocationKey.current === locationKey) {
      console.log('[RouteFileLoader] Already loaded this path with same key, skipping');
      return;
    }

    // Wait for workflowDocument to be available
    if (!workflowDocument) {
      console.log('[RouteFileLoader] workflowDocument not ready');
      return;
    }

    const loadFile = async () => {
      try {
        const filePath = state.filePath!;
        console.log('[RouteFileLoader] Loading file:', filePath);

        // Import IPC API dynamically
        const { IPCAPI } = await import('../../../services/ipc/api');
        const ipcApi = IPCAPI.getInstance();

        // Read the file
        const fileResponse = await ipcApi.readSkillFile(filePath);

        if (fileResponse.success && fileResponse.data) {
          const data = JSON.parse(fileResponse.data.content) as SkillInfo;
          const diagram = data.workFlow;

          // Normalize skillName from folder when loading via route
          // Expect path like: <...>/<name>_skill/diagram_dir/<name>_skill.json
          try {
            const norm = String(filePath).replace(/\\/g, '/');
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
            setCurrentFilePath(filePath);
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
          } else {
            // Fallback for older formats
            workflowDocument.clear();
            workflowDocument.fromJSON(data as any);
            workflowDocument.fitView && workflowDocument.fitView();

            setSkillInfo(data);
            setCurrentFilePath(filePath);
            setHasUnsavedChanges(false);
          }
        }
        // Mark this path and location key as loaded
        lastLoadedPath.current = filePath;
        lastLocationKey.current = locationKey;
        console.log('[RouteFileLoader] File loaded successfully:', filePath);
      } catch (error) {
        console.error('[RouteFileLoader] Error loading file:', error);
      }
    };

    // Small delay to ensure editor is fully initialized
    const timeoutId = setTimeout(loadFile, 200);

    return () => {
      clearTimeout(timeoutId);
    };
  }, [location.state, location.key, workflowDocument, setSkillInfo, setBreakpoints, setCurrentFilePath, setHasUnsavedChanges]);

  return null; // This component doesn't render anything
};
