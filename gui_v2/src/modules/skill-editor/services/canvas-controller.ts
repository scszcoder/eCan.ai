/**
 * Canvas Controller Service
 * 
 * Exposes flowgram editor methods for external control (e.g., from chat AI).
 * This service acts as a bridge between the chat panel and the editor canvas.
 * 
 * The controller is designed to be:
 * 1. Callable from IPC handlers (backend-initiated commands)
 * 2. Usable as MCP tools for the AI agent
 * 3. Accessible from the ChatPanel component
 */

import { 
  CanvasPosition, 
  NodeConfig, 
  EdgeDefinition,
  SkillEditorEvent,
  SkillEditorEventType,
} from '../types';
import { ipcClient } from '../../../services/ipc';
import { loadSkillFile } from './skill-loader';

// ============================================================
// Types
// ============================================================

export interface CanvasNode {
  id: string;
  type: string;
  label: string;
  position: CanvasPosition;
  data?: Record<string, unknown>;
}

export interface CanvasEdge {
  id: string;
  source: string;
  sourceHandle?: string;
  target: string;
  targetHandle?: string;
  label?: string;
}

export interface CanvasState {
  nodes: CanvasNode[];
  edges: CanvasEdge[];
  flowgramId?: string;
  flowgramName?: string;
}

export type CanvasCommandResult = {
  success: boolean;
  message?: string;
  data?: unknown;
  error?: string;
};

/** Callback type for canvas events */
export type CanvasEventCallback = (event: SkillEditorEvent) => void;

// ============================================================
// Canvas Controller Class
// ============================================================

class CanvasControllerService {
  private static instance: CanvasControllerService | null = null;
  
  // Editor service references (set by EditorBridge component)
  private documentService: any = null;
  private commandService: any = null;
  private playground: any = null;
  private sheetsStore: any = null;
  private skillInfoStore: any = null;
  
  // Event listeners
  private eventListeners: Set<CanvasEventCallback> = new Set();
  
  // Session tracking
  private currentSessionId: string | null = null;
  
  private constructor() {}
  
  static getInstance(): CanvasControllerService {
    if (!CanvasControllerService.instance) {
      CanvasControllerService.instance = new CanvasControllerService();
    }
    return CanvasControllerService.instance;
  }
  
  // ==================== Service Registration ====================
  
  /**
   * Register editor services (called by EditorBridge component)
   */
  registerServices(services: {
    documentService?: any;
    commandService?: any;
    playground?: any;
    sheetsStore?: any;
    skillInfoStore?: any;
  }): void {
    if (services.documentService) this.documentService = services.documentService;
    if (services.commandService) this.commandService = services.commandService;
    if (services.playground) this.playground = services.playground;
    if (services.sheetsStore) this.sheetsStore = services.sheetsStore;
    if (services.skillInfoStore) this.skillInfoStore = services.skillInfoStore;
    
    console.log('[CanvasController] Services registered:', {
      hasDocument: !!this.documentService,
      hasCommand: !!this.commandService,
      hasPlayground: !!this.playground,
      hasSheets: !!this.sheetsStore,
      hasSkillInfo: !!this.skillInfoStore,
    });
  }
  
  /**
   * Check if services are available
   */
  isReady(): boolean {
    return !!(this.documentService && this.commandService);
  }
  
  // ==================== Event System ====================
  
  /**
   * Subscribe to canvas events
   */
  addEventListener(callback: CanvasEventCallback): () => void {
    this.eventListeners.add(callback);
    return () => this.eventListeners.delete(callback);
  }
  
  /**
   * Emit an event to all listeners
   */
  private emitEvent(type: SkillEditorEventType, payload: unknown): void {
    const event: SkillEditorEvent = {
      eventId: crypto.randomUUID(),
      type,
      timestamp: Date.now(),
      sessionId: this.currentSessionId || '',
      payload,
    } as SkillEditorEvent;
    
    this.eventListeners.forEach(callback => {
      try {
        callback(event);
      } catch (e) {
        console.error('[CanvasController] Event listener error:', e);
      }
    });
  }
  
  /**
   * Set current session ID for event tracking
   */
  setSessionId(sessionId: string): void {
    this.currentSessionId = sessionId;
  }
  
  // ==================== Canvas State ====================
  
  /**
   * Get current canvas state
   */
  getCanvasState(): CanvasState {
    console.log('[CanvasController] Getting canvas state');
    if (!this.documentService) {
      console.warn('[CanvasController] Document service not available');
      return { nodes: [], edges: [] };
    }
    
    try {
      const nodes = this.documentService.getNodes?.() || [];
      const edges = this.documentService.getEdges?.() || [];
      
      const state = {
        nodes: nodes.map((n: any) => ({
          id: n.id,
          type: n.type || n.data?.nodeType || 'unknown',
          label: n.data?.label || n.data?.title || n.id,
          position: { x: n.position?.x || 0, y: n.position?.y || 0 },
          data: n.data,
        })),
        edges: edges.map((e: any) => ({
          id: e.id,
          source: e.source,
          sourceHandle: e.sourceHandle,
          target: e.target,
          targetHandle: e.targetHandle,
          label: e.label,
        })),
        flowgramId: this.skillInfoStore?.getState?.()?.skillInfo?.id,
        flowgramName: this.skillInfoStore?.getState?.()?.skillInfo?.skillName,
      };
      console.log('[CanvasController] Canvas state:', { nodeCount: state.nodes.length, edgeCount: state.edges.length });
      return state;
    } catch (e) {
      console.error('[CanvasController] Error getting canvas state:', e);
      return { nodes: [], edges: [] };
    }
  }
  
  // ==================== Node Operations ====================
  
  /**
   * Add a node to the canvas
   */
  async addNode(
    nodeType: string,
    position: CanvasPosition,
    config?: NodeConfig
  ): Promise<CanvasCommandResult> {
    console.log('[CanvasController] Adding node:', { nodeType, position, config });
    if (!this.isReady()) {
      console.error('[CanvasController] Not ready - cannot add node');
      return { success: false, error: 'Canvas controller not ready' };
    }
    
    try {
      const nodeId = `node_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      
      // Create node data based on type
      const nodeData = {
        id: nodeId,
        type: nodeType,
        position,
        data: {
          nodeType,
          label: config?.label || nodeType,
          ...config?.inputsValues,
          ...config?.config,
        },
      };
      
      // Use command service to add node
      if (this.commandService?.executeCommand) {
        await this.commandService.executeCommand('workflow.node.add', nodeData);
      } else if (this.documentService?.addNode) {
        this.documentService.addNode(nodeData);
      }
      
      this.emitEvent('canvas.add_node', { nodeId, nodeType, position, config });
      
      console.log('[CanvasController] Node added successfully:', nodeId);
      return { 
        success: true, 
        message: `Added ${nodeType} node`,
        data: { nodeId }
      };
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e);
      console.error('[CanvasController] Error adding node:', e);
      return { success: false, error };
    }
  }
  
  /**
   * Remove a node from the canvas
   */
  async removeNode(nodeId: string): Promise<CanvasCommandResult> {
    console.log('[CanvasController] Removing node:', nodeId);
    if (!this.isReady()) {
      console.error('[CanvasController] Not ready - cannot remove node');
      return { success: false, error: 'Canvas controller not ready' };
    }
    
    try {
      if (this.commandService?.executeCommand) {
        await this.commandService.executeCommand('workflow.node.delete', { nodeId });
      } else if (this.documentService?.removeNode) {
        this.documentService.removeNode(nodeId);
      }
      
      this.emitEvent('canvas.remove_node', { nodeId });
      
      console.log('[CanvasController] Node removed successfully:', nodeId);
      return { success: true, message: `Removed node ${nodeId}` };
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e);
      console.error('[CanvasController] Error removing node:', e);
      return { success: false, error };
    }
  }
  
  /**
   * Update a node's configuration
   */
  async updateNode(
    nodeId: string,
    config: Partial<NodeConfig>,
    position?: CanvasPosition
  ): Promise<CanvasCommandResult> {
    if (!this.isReady()) {
      return { success: false, error: 'Canvas controller not ready' };
    }
    
    try {
      const updateData: any = { nodeId };
      if (config) updateData.data = config;
      if (position) updateData.position = position;
      
      if (this.commandService?.executeCommand) {
        await this.commandService.executeCommand('workflow.node.update', updateData);
      } else if (this.documentService?.updateNode) {
        this.documentService.updateNode(nodeId, updateData);
      }
      
      this.emitEvent('canvas.update_node', { nodeId, config, position });
      
      return { success: true, message: `Updated node ${nodeId}` };
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e);
      console.error('[CanvasController] Error updating node:', e);
      return { success: false, error };
    }
  }
  
  // ==================== Edge Operations ====================
  
  /**
   * Add an edge between nodes
   */
  async addEdge(edge: EdgeDefinition): Promise<CanvasCommandResult> {
    console.log('[CanvasController] Adding edge:', edge);
    if (!this.isReady()) {
      console.error('[CanvasController] Not ready - cannot add edge');
      return { success: false, error: 'Canvas controller not ready' };
    }
    
    try {
      const edgeId = `edge_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      
      const edgeData = {
        id: edgeId,
        source: edge.sourceNodeId,
        sourceHandle: edge.sourceHandle,
        target: edge.targetNodeId,
        targetHandle: edge.targetHandle,
        label: edge.label,
      };
      
      if (this.commandService?.executeCommand) {
        await this.commandService.executeCommand('workflow.edge.add', edgeData);
      } else if (this.documentService?.addEdge) {
        this.documentService.addEdge(edgeData);
      }
      
      this.emitEvent('canvas.add_edge', { edgeId, ...edge });
      
      console.log('[CanvasController] Edge added successfully:', edgeId);
      return { 
        success: true, 
        message: `Added edge from ${edge.sourceNodeId} to ${edge.targetNodeId}`,
        data: { edgeId }
      };
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e);
      console.error('[CanvasController] Error adding edge:', e);
      return { success: false, error };
    }
  }
  
  /**
   * Remove an edge
   */
  async removeEdge(edgeId: string): Promise<CanvasCommandResult> {
    if (!this.isReady()) {
      return { success: false, error: 'Canvas controller not ready' };
    }
    
    try {
      if (this.commandService?.executeCommand) {
        await this.commandService.executeCommand('workflow.edge.delete', { edgeId });
      } else if (this.documentService?.removeEdge) {
        this.documentService.removeEdge(edgeId);
      }
      
      this.emitEvent('canvas.remove_edge', { edgeId });
      
      return { success: true, message: `Removed edge ${edgeId}` };
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e);
      console.error('[CanvasController] Error removing edge:', e);
      return { success: false, error };
    }
  }
  
  // ==================== Flowgram Operations ====================
  
  /**
   * Load a flowgram from JSON data into the canvas
   * This is used when the AI generates a new flowgram
   */
  async loadFlowgram(flowgramData: {
    nodes: Array<{
      id: string;
      type: string;
      label: string;
      position: { x: number; y: number };
      config?: Record<string, unknown>;
      blocks?: Array<any>;
      internal_edges?: Array<any>;
    }>;
    edges: Array<{
      source: string;
      target: string;
      source_handle?: string;
      target_handle?: string;
      label?: string;
    }>;
    metadata?: {
      skillName?: string;
      description?: string;
      [key: string]: unknown;
    };
  }): Promise<CanvasCommandResult> {
    console.log('[CanvasController] Loading flowgram:', {
      nodeCount: flowgramData.nodes?.length || 0,
      edgeCount: flowgramData.edges?.length || 0,
      metadata: flowgramData.metadata,
    });
    
    if (!this.isReady()) {
      console.error('[CanvasController] Not ready - cannot load flowgram');
      return { success: false, error: 'Canvas controller not ready' };
    }
    
    try {
      const skillName = flowgramData.metadata?.skillName || 'generated_skill';
      const description = flowgramData.metadata?.description || 'Generated by AI';
      
      // Convert nodes to the format expected by the editor
      const convertedNodes = flowgramData.nodes.map(node => ({
        id: node.id,
        type: node.type,
        position: node.position,
        data: {
          nodeType: node.type,
          label: node.label,
          title: node.label,
          ...node.config,
          // Handle loop node blocks
          ...(node.blocks ? { blocks: node.blocks } : {}),
          ...(node.internal_edges ? { edges: node.internal_edges } : {}),
        },
      }));
      
      // Convert edges to the format expected by the editor
      const convertedEdges = flowgramData.edges.map((edge, index) => {
        const source =
          (edge as any).source ??
          (edge as any).sourceNodeID ??
          (edge as any).sourceNodeId ??
          (edge as any).from;
        const target =
          (edge as any).target ??
          (edge as any).targetNodeID ??
          (edge as any).targetNodeId ??
          (edge as any).to;
        const sourceHandle =
          (edge as any).source_handle ??
          (edge as any).sourceHandle ??
          (edge as any).sourcePortID ??
          (edge as any).sourcePortId;
        const targetHandle =
          (edge as any).target_handle ??
          (edge as any).targetHandle ??
          (edge as any).targetPortID ??
          (edge as any).targetPortId;
        return {
          id: `edge_${index}_${source}_${target}`,
          source,
          target,
          sourceHandle,
          targetHandle,
          label: edge.label,
        };
      });
      
      console.log('[CanvasController] Converted nodes:', convertedNodes.length);
      console.log('[CanvasController] Converted edges:', convertedEdges.length);
      
      // Initialize the sheets store with the new document
      if (this.sheetsStore?.initMain) {
        const document = {
          nodes: convertedNodes,
          edges: convertedEdges,
        };
        console.log('[CanvasController] Initializing sheets with document');
        this.sheetsStore.initMain(document);
      }
      
      // Update skill info
      // TEMPORARILY DISABLED: Calling setSkillInfo during loadFlowgram may cause
      // a re-render cascade that breaks the FreeLayoutEditorProvider context
      // TODO: Investigate why setSkillInfo causes React error #321
      if (this.skillInfoStore?.getState) {
        const { setSkillInfo } = this.skillInfoStore.getState();
        if (setSkillInfo) {
          console.log('[CanvasController] SKIPPING setSkillInfo to test if it causes crash:', { skillName, description });
          // setSkillInfo({
          //   skillName,
          //   description,
          //   workFlow: {
          //     nodes: convertedNodes,
          //     edges: convertedEdges,
          //   },
          // });
        }
      }
      
      this.emitEvent('canvas.load_flowgram', { 
        skillName, 
        nodeCount: convertedNodes.length,
        edgeCount: convertedEdges.length,
      });
      
      console.log('[CanvasController] Flowgram loaded successfully');
      return { 
        success: true, 
        message: `Loaded flowgram: ${skillName} with ${convertedNodes.length} nodes`,
        data: { skillName, nodeCount: convertedNodes.length, edgeCount: convertedEdges.length }
      };
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e);
      console.error('[CanvasController] Error loading flowgram:', e);
      return { success: false, error };
    }
  }
  
  /**
   * Create a new flowgram
   */
  async createFlowgram(name: string, description?: string): Promise<CanvasCommandResult> {
    try {
      // Clear current canvas
      if (this.sheetsStore?.initMain) {
        const emptyDoc = { nodes: [], edges: [] };
        this.sheetsStore.initMain(emptyDoc);
      }
      
      // Update skill info
      if (this.skillInfoStore?.getState) {
        const { setSkillInfo } = this.skillInfoStore.getState();
        setSkillInfo?.({
          skillName: name,
          description: description || '',
          workFlow: { nodes: [], edges: [] },
        });
      }
      
      this.emitEvent('canvas.create_flowgram', { name, description });
      
      return { success: true, message: `Created flowgram: ${name}` };
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e);
      console.error('[CanvasController] Error creating flowgram:', e);
      return { success: false, error };
    }
  }
  
  /**
   * Clear all nodes and edges from canvas
   */
  async clearCanvas(): Promise<CanvasCommandResult> {
    if (!this.isReady()) {
      return { success: false, error: 'Canvas controller not ready' };
    }
    
    try {
      const state = this.getCanvasState();
      
      // Remove all edges first
      for (const edge of state.edges) {
        await this.removeEdge(edge.id);
      }
      
      // Then remove all nodes
      for (const node of state.nodes) {
        await this.removeNode(node.id);
      }
      
      this.emitEvent('canvas.clear_canvas', { confirmed: true });
      
      return { success: true, message: 'Canvas cleared' };
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e);
      console.error('[CanvasController] Error clearing canvas:', e);
      return { success: false, error };
    }
  }
  
  // ==================== Run Controls ====================
  
  /**
   * Get current skill data for running
   */
  private getCurrentSkillData(): Record<string, unknown> | null {
    try {
      if (!this.skillInfoStore?.getState) return null;
      const { skillInfo } = this.skillInfoStore.getState();
      if (!skillInfo) return null;
      
      // Get sheets data
      let sheetsData = null;
      if (this.sheetsStore?.getState) {
        const sheetsState = this.sheetsStore.getState();
        sheetsData = {
          sheets: Object.entries(sheetsState.sheets || {}).map(([id, sheet]: [string, any]) => ({
            id,
            name: sheet.name,
            document: sheet.document,
          })),
          order: sheetsState.order,
          activeSheetId: sheetsState.activeSheetId,
        };
      }
      
      return {
        ...skillInfo,
        diagram: {
          workFlow: skillInfo.workFlow,
          bundle: sheetsData,
        },
      };
    } catch (e) {
      console.error('[CanvasController] Error getting skill data:', e);
      return null;
    }
  }
  
  /**
   * Trigger flowgram run (delegates to existing run_skill IPC)
   */
  async runFlowgram(input?: Record<string, unknown>): Promise<CanvasCommandResult> {
    console.log('[CanvasController] Running flowgram with input:', input);
    try {
      const runId = `run_${Date.now()}`;
      this.emitEvent('run.start', { runId, input });
      
      // Get current skill data
      const skillData = this.getCurrentSkillData();
      if (!skillData) {
        return { success: false, error: 'No skill data available' };
      }
      
      // Call existing run_skill IPC handler
      console.log('[CanvasController] Calling run_skill IPC');
      const response = await ipcClient.invoke('run_skill', { skill: skillData });
      console.log('[CanvasController] run_skill response:', { status: response.status });
      
      if (response.status === 'success') {
        return { 
          success: true, 
          message: 'Run initiated',
          data: { runId, result: response.result }
        };
      } else {
        return { 
          success: false, 
          error: response.error?.message || 'Failed to start run'
        };
      }
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e);
      console.error('[CanvasController] Error running flowgram:', e);
      return { success: false, error };
    }
  }
  
  /**
   * Single step execution
   */
  async stepFlowgram(): Promise<CanvasCommandResult> {
    try {
      const runId = `step_${Date.now()}`;
      this.emitEvent('run.step', { runId });
      
      // Call existing step_run_skill IPC handler
      const response = await ipcClient.invoke('step_run_skill', {});
      
      if (response.status === 'success') {
        return { success: true, message: 'Step initiated', data: response.result };
      } else {
        return { success: false, error: response.error?.message || 'Failed to step' };
      }
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e);
      console.error('[CanvasController] Error stepping flowgram:', e);
      return { success: false, error };
    }
  }
  
  /**
   * Pause execution
   */
  async pauseFlowgram(): Promise<CanvasCommandResult> {
    console.log('[CanvasController] Pausing flowgram');
    try {
      this.emitEvent('run.pause', { runId: 'current' });
      
      // Call existing pause_run_skill IPC handler
      const response = await ipcClient.invoke('pause_run_skill', {});
      console.log('[CanvasController] pause_run_skill response:', { status: response.status });
      
      if (response.status === 'success') {
        return { success: true, message: 'Pause requested', data: response.result };
      } else {
        return { success: false, error: response.error?.message || 'Failed to pause' };
      }
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e);
      console.error('[CanvasController] Error pausing flowgram:', e);
      return { success: false, error };
    }
  }
  
  /**
   * Resume execution
   */
  async resumeFlowgram(): Promise<CanvasCommandResult> {
    console.log('[CanvasController] Resuming flowgram');
    try {
      this.emitEvent('run.resume', { runId: 'current' });
      
      // Call existing resume_run_skill IPC handler
      const response = await ipcClient.invoke('resume_run_skill', {});
      console.log('[CanvasController] resume_run_skill response:', { status: response.status });
      
      if (response.status === 'success') {
        return { success: true, message: 'Resume requested', data: response.result };
      } else {
        return { success: false, error: response.error?.message || 'Failed to resume' };
      }
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e);
      console.error('[CanvasController] Error resuming flowgram:', e);
      return { success: false, error };
    }
  }
  
  /**
   * Stop execution
   */
  async stopFlowgram(): Promise<CanvasCommandResult> {
    console.log('[CanvasController] Stopping flowgram');
    try {
      this.emitEvent('run.stop', { runId: 'current', reason: 'User requested' });
      
      // Call existing cancel_run_skill IPC handler
      const response = await ipcClient.invoke('cancel_run_skill', {});
      console.log('[CanvasController] cancel_run_skill response:', { status: response.status });
      
      if (response.status === 'success') {
        return { success: true, message: 'Stop requested', data: response.result };
      } else {
        return { success: false, error: response.error?.message || 'Failed to stop' };
      }
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e);
      console.error('[CanvasController] Error stopping flowgram:', e);
      return { success: false, error };
    }
  }
}

// Export singleton instance
export const canvasController = CanvasControllerService.getInstance();

// Export for use in components
export default canvasController;
