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
    return;
  }

  // ==================== Chat Events ====================

  eventBus.on('ws:push_chat_message', (data: any) => {
    const chatStore = useChatStore.getState();
    if (data.chatId && data.message) {
      chatStore.addMessage(data.chatId, data.message);
      // Also notify MessageManager so the Chat page renders the new message
      eventBus.emit('chat:newMessage', { chatId: data.chatId, message: data.message });
    }
  });

  // ==================== Skill Run Events ====================

  eventBus.on('ws:update_skill_run_stat', (data: any) => {
    
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
  });

  // ==================== Other Events ====================
  // Note: Other events (ws:push_chat_notification, ws:update_tasks_stat, ws:lightrag:*)
  // are handled directly by components that listen to these events.
  // No store updates needed here.

  listenersInitialized = true;
}

/**
 * Cleanup WebSocket event listeners
 */
export function cleanupWebSocketEventListeners(): void {
  // Note: eventBus.off would need to be implemented to properly clean up
  // For now, we just mark as not initialized
  listenersInitialized = false;
}
