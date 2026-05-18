/**
 * WebSocket Event Listeners
 * 
 * Listens for WebSocket push events from the backend and updates the appropriate stores.
 * This bridges the gap between the WebSocket client and the application state.
 */

import { eventBus } from '../../utils/eventBus';
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
  // NOTE: Only emit 'chat:newMessage' event here.
  // MessageManager listens to this event and adds messages.
  // This is the SINGLE entry point for incoming chat messages.
  // DO NOT add messages to chatStore here to avoid duplicates.

  eventBus.on('ws:push_chat_message', (data: any) => {
    if (data.chatId && data.message) {
      const msgId = data.message?.id || 'no-id';
      const content = typeof data.message?.content === 'string' 
        ? data.message.content.substring(0, 50) 
        : JSON.stringify(data.message?.content || '').substring(0, 50);
      console.log(`[WS-EVENT] ws:push_chat_message received - chatId=${data.chatId}, msgId=${msgId}, content="${content}..."`);
      
      // Emit event for MessageManager to pick up
      // DO NOT add to chatStore here - that would cause duplicates
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

  listenersInitialized = true;
}

/**
 * Cleanup WebSocket event listeners
 */
export function cleanupWebSocketEventListeners(): void {
  listenersInitialized = false;
}
