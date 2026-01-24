/**
 * Canvas Event Handler
 * 
 * Handles backend-initiated canvas commands received via IPC.
 * This allows the AI agent to control the canvas through chat.
 */

import { ipcClient } from '../../../services/ipc';
import { eventBus } from '../../../utils/eventBus';
import { canvasController } from './canvas-controller';
import {
  SkillEditorEvent,
  SkillEditorEventType,
  isCanvasEvent,
  isRunEvent,
  CanvasAddNodeEvent,
  CanvasRemoveNodeEvent,
  CanvasUpdateNodeEvent,
  CanvasAddEdgeEvent,
  CanvasRemoveEdgeEvent,
  CanvasClearCanvasEvent,
  CanvasCreateFlowgramEvent,
  RunStartEvent,
  RunStepEvent,
  RunPauseEvent,
  RunResumeEvent,
  RunStopEvent,
} from '../types';

// Event listener type
type EventHandler = (event: SkillEditorEvent) => void;

class CanvasEventHandler {
  private static instance: CanvasEventHandler | null = null;
  private eventHandlers: Map<SkillEditorEventType, Set<EventHandler>> = new Map();
  private isListening: boolean = false;
  
  private constructor() {}
  
  static getInstance(): CanvasEventHandler {
    if (!CanvasEventHandler.instance) {
      CanvasEventHandler.instance = new CanvasEventHandler();
    }
    return CanvasEventHandler.instance;
  }
  
  /**
   * Start listening for backend events
   */
  startListening(): void {
    if (this.isListening) return;
    
    // Register IPC handler for skill editor events
    // The backend will send events through this channel
    this.setupIPCListener();
    this.isListening = true;
    
    console.log('[CanvasEventHandler] Started listening for backend events');
  }
  
  /**
   * Stop listening for backend events
   */
  stopListening(): void {
    this.isListening = false;
    console.log('[CanvasEventHandler] Stopped listening for backend events');
  }
  
  /**
   * Register a handler for a specific event type
   */
  on(eventType: SkillEditorEventType, handler: EventHandler): () => void {
    if (!this.eventHandlers.has(eventType)) {
      this.eventHandlers.set(eventType, new Set());
    }
    this.eventHandlers.get(eventType)!.add(handler);
    
    // Return unsubscribe function
    return () => {
      this.eventHandlers.get(eventType)?.delete(handler);
    };
  }
  
  /**
   * Set up IPC listener for backend events
   */
  private setupIPCListener(): void {
    // Listen for events from the backend
    // This will be called when the backend sends a skill_editor.event message
    if (typeof window !== 'undefined') {
      // Register a handler that the backend can call
      (window as any).__skillEditorEventHandler = this.handleBackendEvent.bind(this);
    }
    
    // Subscribe to eventBus for skill_editor:event (emitted by handlers.ts)
    eventBus.on('skill_editor:event', (data: any) => {
      console.log('[CanvasEventHandler] 🎯 Received skill_editor:event from eventBus:', data);
      console.log('[CanvasEventHandler] 🎯 Data keys:', Object.keys(data || {}));
      console.log('[CanvasEventHandler] 🎯 Has flowgram:', !!data?.flowgram, 'Has type:', !!data?.type, 'Type value:', data?.type);
      
      // Extract type from data - it could be at top level or we need to infer from commandType
      let eventType = data.type as SkillEditorEventType;
      
      // If no type, try to map commandType to event type
      if (!eventType && data.commandType) {
        const commandTypeMap: Record<string, string> = {
          'load_flowgram': 'canvas.load_flowgram_data',
          'clarification': 'chat.clarification',
          'plan': 'chat.plan',
        };
        eventType = (commandTypeMap[data.commandType] || data.commandType) as SkillEditorEventType;
      }
      
      // Skip if we still don't have a valid type
      if (!eventType) {
        console.log('[CanvasEventHandler] Skipping event with no type:', data);
        return;
      }
      
      // Convert eventBus data to SkillEditorEvent format
      const event: SkillEditorEvent = {
        eventId: `evt-${Date.now()}`,
        type: eventType,
        timestamp: Date.now(),
        sessionId: data.sessionId || '',
        payload: data,
      } as SkillEditorEvent;
      
      this.handleBackendEvent(event);
    });
  }
  
  /**
   * Handle an event from the backend
   */
  async handleBackendEvent(event: SkillEditorEvent): Promise<void> {
    console.log('[CanvasEventHandler] Received event:', event.type, event);
    
    try {
      // Process canvas events
      if (isCanvasEvent(event)) {
        await this.processCanvasEvent(event);
      }
      
      // Process run events
      if (isRunEvent(event)) {
        await this.processRunEvent(event);
      }
      
      // Notify registered handlers
      const handlers = this.eventHandlers.get(event.type);
      if (handlers) {
        handlers.forEach(handler => {
          try {
            handler(event);
          } catch (e) {
            console.error('[CanvasEventHandler] Handler error:', e);
          }
        });
      }
    } catch (error) {
      console.error('[CanvasEventHandler] Error processing event:', error);
    }
  }
  
  /**
   * Process canvas control events
   */
  private async processCanvasEvent(event: SkillEditorEvent): Promise<void> {
    switch (event.type) {
      case 'canvas.add_node': {
        const e = event as CanvasAddNodeEvent;
        await canvasController.addNode(
          e.payload.nodeType,
          e.payload.position,
          e.payload.config
        );
        break;
      }
      
      case 'canvas.remove_node': {
        const e = event as CanvasRemoveNodeEvent;
        await canvasController.removeNode(e.payload.nodeId);
        break;
      }
      
      case 'canvas.update_node': {
        const e = event as CanvasUpdateNodeEvent;
        await canvasController.updateNode(
          e.payload.nodeId,
          e.payload.config,
          e.payload.position
        );
        break;
      }
      
      case 'canvas.add_edge': {
        const e = event as CanvasAddEdgeEvent;
        await canvasController.addEdge({
          sourceNodeId: e.payload.sourceNodeId,
          targetNodeId: e.payload.targetNodeId,
          sourceHandle: e.payload.sourceHandle,
          targetHandle: e.payload.targetHandle,
          label: e.payload.label,
        });
        break;
      }
      
      case 'canvas.remove_edge': {
        const e = event as CanvasRemoveEdgeEvent;
        await canvasController.removeEdge(e.payload.edgeId);
        break;
      }
      
      case 'canvas.clear_canvas': {
        const e = event as CanvasClearCanvasEvent;
        if (e.payload.confirmed) {
          await canvasController.clearCanvas();
        }
        break;
      }
      
      case 'canvas.create_flowgram': {
        const e = event as CanvasCreateFlowgramEvent;
        await canvasController.createFlowgram(e.payload.name, e.payload.description);
        break;
      }
      
      case 'canvas.load_flowgram_data': {
        // Load flowgram data directly into canvas (from agent-generated flowgram)
        const payload = (event as any).payload;
        console.log('[CanvasEventHandler] Loading flowgram data directly:', payload);
        if (payload?.flowgram) {
          try {
            const { useSheetsStore } = await import('../stores/sheets-store');
            const { useAutoSaveStore } = await import('../stores/editor-auto-save-store');
            
            // Disable auto-save while loading
            const autoSaveStore = useAutoSaveStore.getState();
            const wasAutoSaveEnabled = autoSaveStore.autoSaveEnabled;
            autoSaveStore.setAutoSaveEnabled(false);
            console.log('[CanvasEventHandler] Auto-save disabled during flowgram data load');
            
            const sheetsStore = useSheetsStore.getState();
            const flowgram = payload.flowgram;
            
            // Create a synthetic bundle from the flowgram data
            const syntheticBundle = {
              mainSheetId: 'main',
              sheets: [{
                id: 'main',
                name: 'Main',
                document: {
                  nodes: flowgram.nodes || [],
                  edges: flowgram.edges || [],
                },
                createdAt: Date.now(),
                lastOpenedAt: Date.now(),
              }],
              openTabs: ['main'],
              activeSheetId: 'main',
            };
            
            console.log('[CanvasEventHandler] Loading synthetic bundle with', flowgram.nodes?.length, 'nodes');
            sheetsStore.loadBundle(syntheticBundle as any);
            
            // Re-enable auto-save after a delay
            setTimeout(() => {
              if (wasAutoSaveEnabled) {
                autoSaveStore.setAutoSaveEnabled(true);
                console.log('[CanvasEventHandler] Auto-save re-enabled after flowgram data load');
              }
            }, 500);
            
            console.log('[CanvasEventHandler] Flowgram data loaded successfully');
          } catch (error) {
            console.error('[CanvasEventHandler] Error loading flowgram data:', error);
          }
        }
        break;
      }
      
      case 'canvas.load_flowgram': {
        // Load a skill from disk into the canvas
        const payload = (event as any).payload;
        console.log('[CanvasEventHandler] Loading flowgram:', payload);
        if (payload?.skillPath && payload?.skillName) {
          try {
            const { loadSkillFile } = await import('./skill-loader');
            const { useSkillInfoStore } = await import('../stores/skill-info-store');
            const { useSheetsStore } = await import('../stores/sheets-store');
            const { useAutoSaveStore } = await import('../stores/editor-auto-save-store');
            const { usePromptStore } = await import('../../../stores/promptStore');
            
            // IMPORTANT: Disable auto-save while loading to prevent race condition
            // where old canvas data gets saved to the new skill file
            const autoSaveStore = useAutoSaveStore.getState();
            const wasAutoSaveEnabled = autoSaveStore.autoSaveEnabled;
            autoSaveStore.setAutoSaveEnabled(false);
            console.log('[CanvasEventHandler] Auto-save disabled during load');
            
            // Construct the skill file path
            const skillFilePath = `${payload.skillPath}/diagram_dir/${payload.skillName}_skill.json`;
            console.log('[CanvasEventHandler] Loading skill file:', skillFilePath);
            
            const result = await loadSkillFile(skillFilePath);
            
            if (result.success && result.skillInfo) {
              console.log('[CanvasEventHandler] Skill loaded successfully, updating stores...');
              
              // Get store actions
              const skillInfoStore = useSkillInfoStore.getState();
              const sheetsStore = useSheetsStore.getState();
              
              // Load bundle FIRST before updating skillInfo to ensure canvas has new data
              // before auto-save can trigger
              if (result.bundle) {
                console.log('[CanvasEventHandler] Loading bundle with', result.bundle.sheets?.length, 'sheets');
                sheetsStore.loadBundle(result.bundle);
              } else if (result.skillInfo.workFlow) {
                console.log('[CanvasEventHandler] Creating synthetic bundle from workflow');
                // Create a synthetic bundle with just the main sheet
                const syntheticBundle = {
                  mainSheetId: 'main',
                  sheets: [{
                    id: 'main',
                    name: 'Main',
                    document: result.skillInfo.workFlow,
                    createdAt: Date.now(),
                    lastOpenedAt: Date.now(),
                  }],
                  openTabs: ['main'],
                  activeSheetId: 'main',
                };
                sheetsStore.loadBundle(syntheticBundle as any);
              }
              
              // Now update skill info store AFTER sheets are loaded
              skillInfoStore.setSkillInfo(result.skillInfo);
              skillInfoStore.setCurrentFilePath(skillFilePath);
              skillInfoStore.setHasUnsavedChanges(false);
              
              // Set breakpoints if any
              const diagram = result.skillInfo.workFlow;
              if (diagram && Array.isArray(diagram.nodes)) {
                const breakpointIds = diagram.nodes
                  .filter((node: any) => node.data?.break_point)
                  .map((node: any) => node.id);
                skillInfoStore.setBreakpoints(breakpointIds);
              }
              
              console.log('[CanvasEventHandler] Skill loaded and stores updated:', payload.skillName);

              // Force-refresh prompt store so newly generated prompts (my_prompts/) are visible immediately.
              // This also ensures promptSelection IDs resolve to human-readable titles.
              try {
                const { IPCAPI } = await import('../../../services/ipc/api');
                const { useUserStore } = await import('../../../stores/userStore');
                const api = IPCAPI.getInstance();
                const last = await api.getLastLoginInfo<any>();
                const storeUsername = useUserStore.getState().username || '';
                const lastUsername = (last.success && (last.data as any)?.username) || '';
                const username = storeUsername || lastUsername || 'user';
                await usePromptStore.getState().fetch(username, true);
              } catch (e) {
                console.warn('[CanvasEventHandler] Prompt refresh failed:', e);
              }
            } else {
              console.error('[CanvasEventHandler] Failed to load skill:', result.error);
            }
            
            // Re-enable auto-save after a short delay to let React state settle
            setTimeout(() => {
              if (wasAutoSaveEnabled) {
                useAutoSaveStore.getState().setAutoSaveEnabled(true);
                console.log('[CanvasEventHandler] Auto-save re-enabled');
              }
            }, 2000);
            
          } catch (err) {
            console.error('[CanvasEventHandler] Failed to load skill:', err);
            // Re-enable auto-save on error
            try {
              const { useAutoSaveStore } = await import('../stores/editor-auto-save-store');
              useAutoSaveStore.getState().setAutoSaveEnabled(true);
            } catch {}
          }
        }
        break;
      }
      
      case 'canvas.clear': {
        // Clear the canvas
        console.log('[CanvasEventHandler] Clearing canvas');
        await canvasController.clearCanvas();
        break;
      }
      
      default:
        console.log('[CanvasEventHandler] Unhandled canvas event:', event.type);
    }
  }
  
  /**
   * Process run control events
   */
  private async processRunEvent(event: SkillEditorEvent): Promise<void> {
    switch (event.type) {
      case 'run.start': {
        const e = event as RunStartEvent;
        await canvasController.runFlowgram(e.payload.input);
        break;
      }
      
      case 'run.step': {
        await canvasController.stepFlowgram();
        break;
      }
      
      case 'run.pause': {
        await canvasController.pauseFlowgram();
        break;
      }
      
      case 'run.resume': {
        await canvasController.resumeFlowgram();
        break;
      }
      
      case 'run.stop': {
        await canvasController.stopFlowgram();
        break;
      }
      
      default:
        console.log('[CanvasEventHandler] Unhandled run event:', event.type);
    }
  }
}

// Export singleton instance
export const canvasEventHandler = CanvasEventHandler.getInstance();

export default canvasEventHandler;
