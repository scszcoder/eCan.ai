/**
 * EditorBridge Component
 * 
 * Bridges the editor services with the CanvasController.
 * Must be placed inside FreeLayoutEditorProvider to access editor services.
 */

import React, { useEffect } from 'react';
import { useService, WorkflowDocument, CommandService, usePlayground } from '@flowgram.ai/free-layout-editor';
import { canvasController } from '../services/canvas-controller';
import { canvasEventHandler } from '../services/canvas-event-handler';
import { useSheetsStore } from '../stores/sheets-store';
import { useSkillInfoStore } from '../stores/skill-info-store';

export const EditorBridge: React.FC = () => {
  const documentService = useService(WorkflowDocument);
  const commandService = useService(CommandService);
  const playground = usePlayground();
  
  useEffect(() => {
    // Register services with canvas controller
    canvasController.registerServices({
      documentService,
      commandService,
      playground,
      sheetsStore: useSheetsStore,
      skillInfoStore: useSkillInfoStore,
    });
    
    // Start listening for backend events
    canvasEventHandler.startListening();
    
    // Expose canvas controller globally for debugging
    if (process.env.NODE_ENV === 'development') {
      (window as any).__canvasController = canvasController;
      (window as any).__canvasEventHandler = canvasEventHandler;
    }
    
    return () => {
      // Cleanup on unmount
      canvasEventHandler.stopListening();
      if (process.env.NODE_ENV === 'development') {
        delete (window as any).__canvasController;
        delete (window as any).__canvasEventHandler;
      }
    };
  }, [documentService, commandService, playground]);
  
  return null;
};

export default EditorBridge;
