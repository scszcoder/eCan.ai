/**
 * Unsaved Changes Tracker Hook
 * Tracks when the skill editor content has been modified
 */

import { useEffect, useRef } from 'react';
import { useClientContext } from '@flowgram.ai/free-layout-editor';
import { useSkillInfoStore } from '../stores/skill-info-store';
import { hasFullFilePaths } from '../../../config/platform';

/**
 * Hook to track unsaved changes in the skill editor
 */
export function useUnsavedChangesTracker() {
  const clientContext = useClientContext();
  const workflowDocument = clientContext?.document;
  const setHasUnsavedChanges = useSkillInfoStore((state) => state.setHasUnsavedChanges);
  const hasUnsavedChanges = useSkillInfoStore((state) => state.hasUnsavedChanges);
  const currentFilePath = useSkillInfoStore((state) => state.currentFilePath);
  
  const lastSavedContentRef = useRef<string>('');
  const isInitialLoadRef = useRef(true);

  useEffect(() => {
    if (!workflowDocument || !hasFullFilePaths()) {
      return;
    }

    // Function to check if content has changed
    const checkForChanges = () => {
      try {
        const currentContent = JSON.stringify(workflowDocument.toJSON());
        
        // Skip initial load
        if (isInitialLoadRef.current) {
          lastSavedContentRef.current = currentContent;
          isInitialLoadRef.current = false;
          return;
        }

        const hasChanges = currentContent !== lastSavedContentRef.current;
        
        if (hasChanges !== hasUnsavedChanges) {
          setHasUnsavedChanges(hasChanges);
        }
      } catch (error) {
        console.warn('Error checking for unsaved changes:', error);
      }
    };

    // Listen for document changes
    const unsubscribe = workflowDocument.onChanged(() => {
      // Small delay to batch rapid changes
      setTimeout(checkForChanges, 100);
    });

    return () => {
      unsubscribe?.();
    };
  }, [workflowDocument, setHasUnsavedChanges, hasUnsavedChanges]);

  // Update last saved content when file is saved or loaded
  const markAsSaved = () => {
    if (workflowDocument) {
      try {
        lastSavedContentRef.current = JSON.stringify(workflowDocument.toJSON());
        setHasUnsavedChanges(false);
      } catch (error) {
        console.warn('Error marking as saved:', error);
      }
    }
  };

  // Reset when file path changes (new file loaded)
  useEffect(() => {
    if (currentFilePath) {
      markAsSaved();
    }
  }, [currentFilePath]);

  return {
    markAsSaved,
    hasUnsavedChanges,
  };
}
