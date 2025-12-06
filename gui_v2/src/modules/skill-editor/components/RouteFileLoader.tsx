/**
 * Route File Loader Component
 * Loads a file from route state inside the FreeLayoutEditorProvider context
 */

import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { useClientContext } from '@flowgram.ai/free-layout-editor';
import { useSkillInfoStore } from '../stores/skill-info-store';
import { useSheetsStore } from '../stores/sheets-store';
import { loadSkillFile } from '../services/skill-loader';

export const RouteFileLoader = () => {
  const location = useLocation();
  const { document: workflowDocument } = useClientContext();
  const setSkillInfo = useSkillInfoStore((state) => state.setSkillInfo);
  const setBreakpoints = useSkillInfoStore((state) => state.setBreakpoints);
  const setCurrentFilePath = useSkillInfoStore((state) => state.setCurrentFilePath);
  const setHasUnsavedChanges = useSkillInfoStore((state) => state.setHasUnsavedChanges);
  const loadBundle = useSheetsStore((s) => s.loadBundle);
  
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

        // Use unified skill loader (handles migration automatically)
        const result = await loadSkillFile(filePath);
        
        if (result.success && result.skillInfo) {
          const data = result.skillInfo;
          // skillName is already normalized by skill-loader.ts

          // Load bundle if available, otherwise load single skill
          if (result.bundle) {
            loadBundle(result.bundle);
          }
          
          const diagram = data.workFlow;
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

            // Load diagram into the editor (only if no bundle, bundle loading handles this)
            if (!result.bundle) {
              workflowDocument.clear();
              workflowDocument.fromJSON(diagram);
            }
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
