/**
 * Canvas Event Handler
 * 
 * Handles backend-initiated canvas commands received via IPC.
 * This allows the AI agent to control the canvas through chat.
 */

import { ipcClient } from '../../../services/ipc';
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
