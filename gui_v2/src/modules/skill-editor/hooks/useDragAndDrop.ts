/**
 * Drag and Drop File Hook
 * Handles drag-and-drop file operations with full path support
 */

import { useEffect, useCallback } from 'react';
import { useClientContext } from '@flowgram.ai/free-layout-editor';
import { useSkillInfoStore } from '../stores/skill-info-store';
import { useRecentFilesStore, createRecentFile } from '../stores/recent-files-store';
import { hasIPCSupport, hasFullFilePaths } from '../../../config/platform';
import { SkillInfo } from '../typings/skill-info';
import '../../../services/ipc/file-api'; // Import file API extensions

interface DragAndDropOptions {
  enabled?: boolean;
  onFileDropped?: (filePath: string, skillInfo: SkillInfo) => void;
  onDropError?: (error: Error) => void;
}

/**
 * Hook to handle drag-and-drop file operations
 */
export function useDragAndDrop(options: DragAndDropOptions = {}) {
  const { enabled = true, onFileDropped, onDropError } = options;
  
  const clientContext = useClientContext();
  const workflowDocument = clientContext?.document;
  const setSkillInfo = useSkillInfoStore((state) => state.setSkillInfo);
  const setBreakpoints = useSkillInfoStore((state) => state.setBreakpoints);
  const setCurrentFilePath = useSkillInfoStore((state) => state.setCurrentFilePath);
  const setHasUnsavedChanges = useSkillInfoStore((state) => state.setHasUnsavedChanges);
  const addRecentFile = useRecentFilesStore((state) => state.addRecentFile);

  const handleFileDrop = useCallback(async (filePath: string) => {
    if (!hasIPCSupport() || !hasFullFilePaths()) {
      console.warn('[DragDrop] File path operations not supported in web mode');
      return;
    }

    if (!workflowDocument) {
      console.warn('[DragDrop] Workflow document not available');
      return;
    }

    try {
      // Import IPC API dynamically
      const { IPCAPI } = await import('../../../services/ipc/api');
      const ipcApi = IPCAPI.getInstance();

      // Read the dropped file
      const fileResponse = await ipcApi.readSkillFile(filePath);

      if (fileResponse.success && fileResponse.data) {
        const data = JSON.parse(fileResponse.data.content) as SkillInfo;
        const diagram = data.workFlow;

        if (diagram) {
          // Set skill info with file path
          setSkillInfo(data);
          setCurrentFilePath(filePath);
          setHasUnsavedChanges(false);

          // Add to recent files
          addRecentFile(createRecentFile(filePath, data.skillName));

          // Find and set breakpoints
          const breakpointIds = diagram.nodes
            .filter((node: any) => node.data?.break_point)
            .map((node: any) => node.id);
          setBreakpoints(breakpointIds);

          // Load diagram into the editor
          workflowDocument.clear();
          workflowDocument.fromJSON(diagram);
          workflowDocument.fitView && workflowDocument.fitView();

          console.log('[DragDrop] Successfully loaded:', filePath);
          onFileDropped?.(filePath, data);
        } else {
          // Fallback for older formats
          workflowDocument.clear();
          workflowDocument.fromJSON(data as any);
          workflowDocument.fitView && workflowDocument.fitView();

          setSkillInfo(data);
          setCurrentFilePath(filePath);
          setHasUnsavedChanges(false);
          addRecentFile(createRecentFile(filePath, data.skillName));

          console.log('[DragDrop] Successfully loaded (legacy format):', filePath);
          onFileDropped?.(filePath, data);
        }
      } else {
        throw new Error(fileResponse.error || 'Failed to read file');
      }
    } catch (error) {
      console.error('[DragDrop] Error loading dropped file:', error);
      onDropError?.(error as Error);
    }
  }, [
    workflowDocument,
    setSkillInfo,
    setBreakpoints,
    setCurrentFilePath,
    setHasUnsavedChanges,
    addRecentFile,
    onFileDropped,
    onDropError,
  ]);

  useEffect(() => {
    if (!enabled || !hasIPCSupport() || !hasFullFilePaths()) {
      return;
    }

    const handleDragOver = (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      
      // Add visual feedback
      if (e.dataTransfer) {
        e.dataTransfer.dropEffect = 'copy';
      }
    };

    const handleDragEnter = (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
    };

    const handleDragLeave = (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
    };

    const handleDrop = (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();

      const files = e.dataTransfer?.files;
      if (!files || files.length === 0) {
        return;
      }

      // Handle the first file only
      const file = files[0];
      
      // Check if it's a JSON file
      if (!file.name.toLowerCase().endsWith('.json')) {
        console.warn('[DragDrop] Only JSON files are supported');
        return;
      }

      // In desktop mode, we can get the full file path
      // Note: This requires the file to be accessible via the file system
      // For security reasons, browsers don't expose full paths, but in our desktop app
      // we can handle this through the IPC layer if needed
      
      // For now, we'll use the FileReader API and then try to match with recent files
      // In a full desktop implementation, you'd want to extend the IPC to handle dropped file paths
      const reader = new FileReader();
      reader.onload = (event) => {
        try {
          const content = event.target?.result as string;
          const data = JSON.parse(content) as SkillInfo;
          
          // Since we can't get the full path from drag-and-drop in browser context,
          // we'll treat this as opening a new file without path
          const diagram = data.workFlow;

          if (diagram) {
            setSkillInfo(data);
            setCurrentFilePath(null); // No path available from drag-drop
            setHasUnsavedChanges(false);

            const breakpointIds = diagram.nodes
              .filter((node: any) => node.data?.break_point)
              .map((node: any) => node.id);
            setBreakpoints(breakpointIds);

            workflowDocument.clear();
            workflowDocument.fromJSON(diagram);
            workflowDocument.fitView && workflowDocument.fitView();

            console.log('[DragDrop] Successfully loaded file via FileReader');
            onFileDropped?.(file.name, data);
          }
        } catch (error) {
          console.error('[DragDrop] Error parsing dropped file:', error);
          onDropError?.(error as Error);
        }
      };
      
      reader.readAsText(file);
    };

    // Add event listeners to the document
    document.addEventListener('dragover', handleDragOver);
    document.addEventListener('dragenter', handleDragEnter);
    document.addEventListener('dragleave', handleDragLeave);
    document.addEventListener('drop', handleDrop);

    return () => {
      document.removeEventListener('dragover', handleDragOver);
      document.removeEventListener('dragenter', handleDragEnter);
      document.removeEventListener('dragleave', handleDragLeave);
      document.removeEventListener('drop', handleDrop);
    };
  }, [enabled, handleFileDrop]);

  return {
    handleFileDrop,
  };
}
