/**
 * WebSocket Event Listeners
 * 
 * Listens for WebSocket push events from the backend and updates the appropriate stores.
 * This bridges the gap between the WebSocket client and the application state.
 */

import { eventBus } from '../../utils/eventBus';
import { useAgentStore } from '../../stores/agentStore';
import { useSettingsStore } from '../../stores/settingsStore';
import { useTaskStore } from '../../stores/domain/taskStore';
import { useSkillStore } from '../../stores/domain/skillStore';
import { useKnowledgeStore } from '../../stores/domain/knowledgeStore';
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

  // ==================== Data Update Events ====================

  eventBus.on('ws:update_agents', (data: any) => {
    console.log('[WSListeners] Received update_agents:', data);
    const agentStore = useAgentStore.getState();
    if (data.agents && Array.isArray(data.agents)) {
      agentStore.setAgents(data.agents);
    }
  });

  eventBus.on('ws:update_skills', (data: any) => {
    console.log('[WSListeners] Received update_skills:', data);
    const skillStore = useSkillStore.getState();
    if (data.skills && Array.isArray(data.skills)) {
      skillStore.setSkills(data.skills);
    }
  });

  eventBus.on('ws:update_tasks', (data: any) => {
    console.log('[WSListeners] Received update_tasks:', data);
    const taskStore = useTaskStore.getState();
    if (data.tasks && Array.isArray(data.tasks)) {
      taskStore.setTasks(data.tasks);
    }
  });

  eventBus.on('ws:update_tools', (data: any) => {
    console.log('[WSListeners] Received update_tools:', data);
    // Tools are typically stored in agentStore or a dedicated tools store
    // For now, emit an event that components can listen to
    eventBus.emit('tools:updated', data.tools);
  });

  eventBus.on('ws:update_settings', (data: any) => {
    console.log('[WSListeners] Received update_settings:', data);
    const settingsStore = useSettingsStore.getState();
    if (data.settings) {
      settingsStore.setSettings(data.settings);
    }
  });

  eventBus.on('ws:update_vehicles', (data: any) => {
    console.log('[WSListeners] Received update_vehicles:', data);
    // Vehicles might be stored in agentStore or a dedicated store
    eventBus.emit('vehicles:updated', data.vehicles);
  });

  eventBus.on('ws:update_knowledge', (data: any) => {
    console.log('[WSListeners] Received update_knowledge:', data);
    const knowledgeStore = useKnowledgeStore.getState();
    if (data.knowledge && Array.isArray(data.knowledge)) {
      knowledgeStore.setKnowledge(data.knowledge);
    }
  });

  eventBus.on('ws:update_chats', (data: any) => {
    console.log('[WSListeners] Received update_chats:', data);
    const chatStore = useChatStore.getState();
    if (data.chats) {
      chatStore.setChats(data.chats);
    }
  });

  eventBus.on('ws:update_all', (data: any) => {
    console.log('[WSListeners] Received update_all:', data);
    // Update all stores with the provided data
    if (data.agents) {
      useAgentStore.getState().setAgents(data.agents);
    }
    if (data.skills) {
      useSkillStore.getState().setSkills(data.skills);
    }
    if (data.tasks) {
      useTaskStore.getState().setTasks(data.tasks);
    }
    if (data.settings) {
      useSettingsStore.getState().setSettings(data.settings);
    }
    if (data.knowledge) {
      useKnowledgeStore.getState().setKnowledge(data.knowledge);
    }
    if (data.chats) {
      useChatStore.getState().setChats(data.chats);
    }
  });

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
