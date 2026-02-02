/**
 * WebSocket Event Listeners
 * 
 * Listens for WebSocket push events from the backend and updates the appropriate stores.
 * This bridges the gap between the WebSocket client and the application state.
 */

import { eventBus } from '../../utils/eventBus';
import { useChatStore } from '../../stores/domain/chatStore';
import { useRunningNodeStore } from '@/modules/skill-editor/stores/running-node-store';
import { useRuntimeStateStore } from '@/modules/skill-editor/stores/runtime-state-store';

let listenersInitialized = false;

/**
 * Initialize WebSocket event listeners
 * Should be called once when the app starts
 */
export function initWebSocketEventListeners(): void {
  if (listenersInitialized) {
    console.log('[WSListeners] Already initialized');
    return;
  }

  console.log('[WSListeners] Initializing WebSocket event listeners...');

  // ==================== Chat Events ====================

  eventBus.on('ws:push_chat_message', (data: any) => {
    console.log('[WSListeners] Received push_chat_message:', data);
    const chatStore = useChatStore.getState();
    if (data.chatId && data.message) {
      chatStore.addMessage(data.chatId, data.message);
    }
  });

  eventBus.on('ws:push_chat_notification', (data: any) => {
    console.log('[WSListeners] Received push_chat_notification:', data);
    // Emit notification event for UI components to handle
    eventBus.emit('chat:notification', data);
  });

  // ==================== Skill Run Events ====================

  eventBus.on('ws:update_skill_run_stat', (data: any) => {
    console.log('[WSListeners] Received update_skill_run_stat:', {
      agentTaskId: data.agentTaskId,
      currentNode: data.currentNode || data.current_node,
      status: data.status
    });
    
    const runningNodeStore = useRunningNodeStore.getState();
    const runtimeStateStore = useRuntimeStateStore.getState();
    
    const currentNode = data.currentNode || data.current_node;
    const nodeState = data.langgraphState || data.nodeState;
    
    // Update running node store (uses setRunningNodeId, not setCurrentNode)
    if (currentNode) {
      runningNodeStore.setRunningNodeId(currentNode);
    }
    
    // Update runtime state store (uses setNodeRuntimeState)
    if (currentNode && nodeState) {
      runtimeStateStore.setNodeRuntimeState(currentNode, nodeState, data.status);
    }
    
    // Emit event for skill editor components
    eventBus.emit('skill:run_stat', data);
  });

  eventBus.on('ws:update_tasks_stat', (data: any) => {
    console.log('[WSListeners] Received update_tasks_stat:', data);
    // Emit event for task-related components
    eventBus.emit('task:stat_update', data);
  });

  // ==================== LightRAG Events ====================

  eventBus.on('ws:lightrag:chunk', (data: any) => {
    console.log('[WSListeners] Received lightrag chunk');
    eventBus.emit('lightrag:chunk', data);
  });

  eventBus.on('ws:lightrag:done', (data: any) => {
    console.log('[WSListeners] Received lightrag done');
    eventBus.emit('lightrag:done', data);
  });

  eventBus.on('ws:lightrag:error', (data: any) => {
    console.log('[WSListeners] Received lightrag error');
    eventBus.emit('lightrag:error', data);
  });

  listenersInitialized = true;
  console.log('[WSListeners] ✅ WebSocket event listeners initialized');
}

/**
 * Cleanup WebSocket event listeners
 */
export function cleanupWebSocketEventListeners(): void {
  // Note: eventBus.off would need to be implemented to properly clean up
  // For now, we just mark as not initialized
  listenersInitialized = false;
  console.log('[WSListeners] Cleaned up WebSocket event listeners');
}
