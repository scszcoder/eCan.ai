/**
 * IPC Process器
 * Implementation了与 Python Backend通信的RequestProcess器
 */
import { IPCRequest } from './types';
import { useNodeStatusStore } from '@/modules/skill-editor/stores/node-status-store';
import { useSheetsStore } from '@/modules/skill-editor/stores/sheets-store';
import { useSkillInfoStore } from '@/modules/skill-editor/stores/skill-info-store';
import { useAgentStore } from '../../stores/agentStore';
import { useSettingsStore } from '../../stores/settingsStore';
import {
  useTaskStore,
  useSkillStore,
  useKnowledgeStore,
  useChatStore
} from '../../stores';
import { eventBus } from '@/utils/eventBus';
import { useRunningNodeStore } from '@/modules/skill-editor/stores/running-node-store';
import { useAvatarSceneStore } from '../../stores/avatarSceneStore';
import { useRuntimeStateStore } from '@/modules/skill-editor/stores/runtime-state-store';
import { logger } from '@/utils/logger';
import { handleOnboardingRequest, type OnboardingContext } from '../onboarding/onboardingService';

// Process器TypeDefinition
type Handler = (request: IPCRequest) => Promise<unknown>;
type HandlerMap = Record<string, Handler>;

// ConfigurationStorage
const config = new Map<string, unknown>();

// ParameterValidateFunction
function validateParams(request: IPCRequest, requiredParams: string[]): void {
    const params = request.params as Record<string, unknown> | undefined;
    if (!params) {
        throw new Error(`Missing parameters: ${requiredParams.join(', ')}`);
    }

    const missingParams = requiredParams.filter(param => !(param in params));
    if (missingParams.length > 0) {
        throw new Error(`Missing required parameters: ${missingParams.join(', ')}`);
    }
}

// Process器类
export class IPCHandlers {
    private handlers: HandlerMap = {};

    constructor() {
        this.registerHandler('update_org_agents', this.updateOrgAgents);
        this.registerHandler('get_config', this.getConfig);
        this.registerHandler('set_config', this.setConfig);
        this.registerHandler('notify_event', this.notifyEvent);
        this.registerHandler('update_agents', this.updateAgents);
        this.registerHandler('update_agents_scenes', this.updateAgentsScenes);
        this.registerHandler('update_skills', this.updateSkills);
        this.registerHandler('update_tasks', this.updateTasks);
        this.registerHandler('update_knowledge', this.updateKnowledges);
        this.registerHandler('update_settings', this.updateSettings);
        this.registerHandler('update_chats', this.updateChats);
        // this.registerHandler('update_tools', this.updateTools);
        // this.registerHandler('update_vehicles', this.updateVehicles);
        this.registerHandler('push_chat_message', this.pushChatMessage);
        this.registerHandler('update_skill_run_stat', this.updateSkillRunStat);
        this.registerHandler('update_tasks_stat', this.updateTasksStat);
        this.registerHandler('push_chat_notification', this.pushChatNotification);
        this.registerHandler('update_all', this.updateAll);
        this.registerHandler('update_screens', this.updateScreens);
        this.registerHandler('onboarding_message', this.onboardingMessage);
    }

    private registerHandler(method: string, handler: Handler): void {
        this.handlers[method] = handler;
    }

    getHandlers(): HandlerMap {
        return this.handlers;
    }

    /**
     * Handle onboarding message from backend
     * Standard request handler - delegates to onboarding service
     */
    async onboardingMessage(request: IPCRequest): Promise<unknown> {
        try {
            // Extract onboarding data from request params
            const params = request.params as {
                onboardingType: string;
                context?: OnboardingContext;
            };
            
            const { onboardingType, context } = params;
            
            logger.info(`[Handlers] Received onboarding request: ${onboardingType}`, { 
                requestId: request.id
            });
            
            // Delegate to onboarding service for business logic
            await handleOnboardingRequest(onboardingType, context);
            
            // Return success response
            return {
                success: true,
                onboardingType,
                timestamp: Date.now()
            };
        } catch (error) {
            logger.error('[Handlers] Error handling onboarding request:', error);
            throw error;
        }
    }

    async updateOrgAgents(request: IPCRequest): Promise<unknown> {
        logger.info('Received update_org_agents request:', request.params);
        
        // SimpleSendEvent，让 agents Component自己决定如何Process
        eventBus.emit('org-agents-update', {
            timestamp: Date.now(),
            source: 'backend_notification',
            data: request.params
        });
        
        return { 
            success: true,
            timestamp: Date.now()
        };
    }

    async getConfig(request: IPCRequest): Promise<unknown> {
        validateParams(request, ['key']);
        const { key } = request.params as { key: string };
        if (!config.has(key)) {
            throw new Error(`Config not found for key: ${key}`);
        }
        return config.get(key);
    }

    async setConfig(request: IPCRequest): Promise<unknown> {
        validateParams(request, ['key', 'value']);
        const { key, value } = request.params as { key: string; value: unknown };
        config.set(key, value);
        return { success: true };
    }

    async notifyEvent(request: IPCRequest): Promise<unknown> {
        validateParams(request, ['event']);
        const { event, data } = request.params as { event: string; data?: unknown };
        logger.info('Notify event received:', { event, data });
        return { event, processed: true };
    }

    async updateAgents(request: IPCRequest): Promise<unknown> {
        logger.info('Received update_agents request:', request.params);
        const agents = request.params as any;
        
        // 只Update专用的 agentStore，Remove重复Update
        useAgentStore.getState().setAgents(agents);
        
        logger.info('Updated agentStore with agents:', agents?.length || 0);
        return { refreshed: true };
    }

    async updateAgentsScenes(request: IPCRequest): Promise<unknown> {
        logger.info('Received update_agents_scenes request:', request.params);
        const agents = request.params as any;
        
        // 只Update专用的 agentStore，Remove重复Update
        useAgentStore.getState().setAgents(agents);
        
        logger.info('Updated agentStore with agents scenes:', agents?.length || 0);
        return { refreshed: true };
    }

    async updateSkills(request: IPCRequest): Promise<unknown> {
        logger.info('Received update_skills request:', request.params);
        const skills = request.params as any;

        // 使用新的 skillStore
        if (Array.isArray(skills)) {
            useSkillStore.getState().setItems(skills);
            logger.info('[IPC] Updated skills in skillStore:', skills.length);
        }

        return { refreshed: true };
    }

    async updateTasks(request: IPCRequest): Promise<unknown> {
        logger.info('Received update_tasks request:', request.params);
        const tasks = request.params as any;

        // 使用新的 taskStore
        if (Array.isArray(tasks)) {
            useTaskStore.getState().setItems(tasks);
            logger.info('[IPC] Updated tasks in taskStore:', tasks.length);
        }

        return { refreshed: true };
    }

    async updateSettings(request: IPCRequest): Promise<unknown> {
        logger.info('Received update_settings request:', request.params);
        const settings = request.params as any;

        // Update settingsStore 中的应用级settings（application-level configuration）
        if (settings) {
            useSettingsStore.getState().setSettings(settings);
            logger.info('[IPC] Updated application settings in settingsStore');
        }

        return { refreshed: true };
    }

    async updateKnowledges(request: IPCRequest): Promise<unknown> {
        logger.info('Received update_knowledges request:', request.params);
        const knowledges = request.params as any;

        // 使用新的 knowledgeStore
        if (Array.isArray(knowledges)) {
            useKnowledgeStore.getState().setItems(knowledges);
            logger.info('[IPC] Updated knowledges in knowledgeStore:', knowledges.length);
        }

        return { refreshed: true };
    }

    async updateChats(request: IPCRequest): Promise<{ success: boolean }> {
        logger.info('Received update_chats request:', request.params);
        const chats = request.params as any;

        // 使用新的 chatStore
        if (Array.isArray(chats)) {
            useChatStore.getState().setItems(chats);
            logger.info('[IPC] Updated chats in chatStore:', chats.length);
        }

        return { success: true };
    }

    async updateAll(request: IPCRequest): Promise<{ success: boolean }> {
        logger.info('Received update_all request:', request.params);
        return { success: true };
    }

    async pushChatMessage(request: IPCRequest): Promise<{ success: boolean }> {
        // logger.info('Received pushChatMessage request:', request.params);
        eventBus.emit('chat:newMessage', request.params);
        return { success: true };
    }

    async pushChatNotification(request: IPCRequest): Promise<{ success: boolean }> {
          try { console.log('[IPC][pushChatNotification] raw request', request); } catch {}

        let { chatId, content, isRead, timestamp, uid } = request.params as { chatId: string, content: any, isRead: boolean, timestamp: string, uid: string };
        if (!chatId || !content) {
            throw new Error('pushChatNotification: chatId and notification are required');
        }
        // 自动Parse字符串 JSON
        if (typeof content === 'string') {
            try {
                content = JSON.parse(content);
            } catch (e) {
                throw new Error('pushChatNotification: content is string but not valid JSON');
            }
        }
        console.log("emitting chat:newNotification")
        eventBus.emit('chat:newNotification', { chatId, content, isRead, timestamp, uid });
        return { success: true };
    }


    async updateSkillRunStat(request: IPCRequest): Promise<{ success: boolean }> {
        const { agentTaskId, current_node, status, nodeState, timestamp } = request.params as { agentTaskId?: string, current_node?: string, status?: string, nodeState?: any, timestamp?: number };

        // Log every update received from backend
        console.log(`[RunningNode][IPC] Received: current_node='${current_node}', status='${status}', ts=${timestamp ?? 'n/a'}`);

        // Drop stale/out-of-order updates based on timestamp
        const g: any = (window as any);
        if (typeof g.__runningNodeLastTs !== 'number') g.__runningNodeLastTs = 0;
        const incomingTs = typeof timestamp === 'number' ? timestamp : Date.now();
        if (incomingTs < g.__runningNodeLastTs) {
            console.log(`[RunningNode] ⤳ Ignoring stale update ts=${incomingTs} < lastTs=${g.__runningNodeLastTs}`);
            return { success: true };
        }
        g.__runningNodeLastTs = incomingTs;

        const runningNodeStore = useRunningNodeStore.getState();
        // const previousRunningNode = runningNodeStore.runningNodeId;

        // Queue scheme to enforce a minimum visible duration per node
        const GN: any = (window as any);
        if (!GN.__runningNodeQueue) GN.__runningNodeQueue = { runId: null as string | null, queue: [] as string[], showing: null as string | null, shownAt: 0, t: null as any, completed: false, clearT: null as any, endStatus: null as null | 'completed' | 'failed' };
        const q = GN.__runningNodeQueue as { runId: string | null; queue: string[]; showing: string | null; shownAt: number; t: any; completed: boolean; clearT: any; endStatus: null | 'completed' | 'failed' };
        // Reset queue if this is a new run
        if (agentTaskId && q.runId !== agentTaskId) {
            if (q.t) { try { clearTimeout(q.t); } catch {} }
            if (q.clearT) { try { clearTimeout(q.clearT); } catch {} }
            GN.__runningNodeQueue = { runId: agentTaskId, queue: [], showing: null, shownAt: 0, t: null, completed: false, clearT: null, endStatus: null };
            // Clear any previous end status overlay when a new run starts
            try { useNodeStatusStore.getState().clear(); } catch {}
        }
        // Re-read q after potential reset
        // const qRef = (window as any).__runningNodeQueue as { runId: string | null; queue: string[]; showing: string | null; shownAt: number; t: any; completed: boolean; clearT: any; endStatus: null | 'completed' | 'failed' };
        // const now = Date.now();
        const MIN_VISIBLE_MS = 1000; // hysteresis: each node should be visible at least this long
        const MAX_STUCK_EXTRA_MS = 2000; // fail-safe: if timers get throttled, advance after this extra time

        const showNode = (nodeId: string) => {
            console.log(`[RunningNode] → Show '${nodeId}'`);
            runningNodeStore.setRunningNodeId(nodeId);
            q.showing = nodeId;
            q.shownAt = Date.now();
        };

        const scheduleTick = () => {
            const elapsed = Date.now() - (q.shownAt || 0);
            const remaining = Math.max(0, MIN_VISIBLE_MS - elapsed);
            if (q.t) { try { clearTimeout(q.t); } catch {} q.t = null; }
            // Use a small floor to avoid zero-delay busy looping
            const delay = Math.max(50, remaining);
            q.t = setTimeout(processQueue, delay);
        };

        const maybeScheduleFinalClear = () => {
            if (!q.completed) return;
            if (q.clearT) return;
            const elapsed = Date.now() - (q.shownAt || 0);
            if (q.queue.length === 0 && q.showing) {
                const remaining = Math.max(0, MIN_VISIBLE_MS - elapsed);
                const delay = Math.max(remaining, 450);
                console.log(`[RunningNode] ✓ Queue drained after completion, clearing after ${delay} ms`);
                // Record end status overlay
                try {
                    const st = useNodeStatusStore.getState();
                    const isCompleted = (q.endStatus ?? 'completed') === 'completed';
                    let targetNodeId: string | null = null;
                    if (isCompleted) {
                        // Prefer the End node in the SAME SHEET that contains the last shown node
                        try {
                            const bundle = useSheetsStore.getState().getAllSheets?.();
                            const sheetsArr: any[] = bundle?.sheets || [];
                            for (const s of sheetsArr) {
                                const doc = s?.document;
                                const nodes: any[] = Array.isArray(doc?.nodes) ? doc.nodes : [];
                                const containsLast = nodes.some((n) => n && n.id === q.showing);
                                if (containsLast) {
                                    const endNode = nodes.find((n) => n && (n.type === 'end' || n.type === 'End'));
                                    if (endNode?.id) { targetNodeId = endNode.id; break; }
                                }
                            }
                        } catch {}
                        // Next fallback: End node in the ACTIVE SHEET
                        if (!targetNodeId) {
                            try {
                                const activeDoc = useSheetsStore.getState().getActiveDocument?.();
                                const nodesA = activeDoc?.nodes;
                                if (Array.isArray(nodesA)) {
                                    const endNodeA = nodesA.find((n: any) => n && (n.type === 'end' || n.type === 'End'));
                                    if (endNodeA?.id) targetNodeId = endNodeA.id;
                                }
                            } catch {}
                        }
                        // Final fallback: global skillInfo workflow
                        if (!targetNodeId) {
                            try {
                                const wf = useSkillInfoStore.getState().skillInfo?.workFlow as any;
                                const endNode = wf?.nodes?.find((n: any) => n && (n.type === 'end' || n.type === 'End'));
                                targetNodeId = endNode?.id || null;
                            } catch {}
                        }
                    }
                    // For failure or no end node found, fall back to the last shown node
                    if (!targetNodeId) targetNodeId = q.showing;
                    if (targetNodeId) st.setEndStatus(targetNodeId, (q.endStatus ?? 'completed') as any);
                } catch {}
                q.clearT = setTimeout(() => {
                    const rs = useRunningNodeStore.getState();
                    if (rs.runningNodeId !== null) rs.setRunningNodeId(null);
                    q.showing = null; q.shownAt = 0; q.completed = false; q.clearT = null; q.endStatus = null;
                }, delay);
            }
        };

        const processQueue = () => {
            if (q.t) { try { clearTimeout(q.t); } catch {} q.t = null; }
            const elapsed = Date.now() - (q.shownAt || 0);
            if (!q.showing) {
                const next = q.queue.shift();
                if (next) {
                    showNode(next);
                    // Ensure we advance after min visible time
                    if (q.queue.length > 0 || q.completed) scheduleTick();
                }
                // If completed and nothing to show, consider final clear
                if (!next) maybeScheduleFinalClear();
                return;
            }
            // If we've satisfied minimum visible time, advance to next if any
            if (elapsed >= MIN_VISIBLE_MS) {
                const next = q.queue.shift();
                if (next) {
                    showNode(next);
                    // Continue draining if more queued or completed
                    if (q.queue.length > 0 || q.completed) scheduleTick();
                } else {
                    // Nothing left; if completed, consider clearing
                    maybeScheduleFinalClear();
                }
                return;
            }
            // Fail-safe: if we're beyond MIN + MAX_STUCK_EXTRA_MS and there IS a next node, force-advance
            if (elapsed >= MIN_VISIBLE_MS + MAX_STUCK_EXTRA_MS && q.queue.length > 0) {
                const next = q.queue.shift();
                if (next) {
                    console.warn(`[RunningNode] ⚠ Forcing advance due to potential timer stall (elapsed=${elapsed}ms) to '${next}'`);
                    showNode(next);
                    if (q.queue.length > 0 || q.completed) scheduleTick();
                }
                return;
            }
            // Not yet; if there is pending work, wait remaining time
            if (q.queue.length > 0) {
                scheduleTick();
            } else if (q.completed) {
                // No next item; ensure we clear after min time
                const remaining = Math.max(0, MIN_VISIBLE_MS - elapsed);
                q.t = setTimeout(() => { maybeScheduleFinalClear(); }, Math.max(50, remaining));
            }
        };

        // Update the running node if the backend provides a specific node ID.
        if (typeof current_node === 'string' && current_node.length > 0) {
            // Avoid duplicates: only enqueue if different from the last item and current showing
            const lastQueued = q.queue.length > 0 ? q.queue[q.queue.length - 1] : null;
            if (current_node !== q.showing && current_node !== lastQueued) {
                console.log(`[RunningNode] ≈ Enqueue '${current_node}'`);
                // If this looks like a fresh start (no showing and empty queue), clear any old end-status overlays
                if (!q.showing && q.queue.length === 0 && !q.completed) {
                    try { useNodeStatusStore.getState().clear(); } catch {}
                }
                q.queue.push(current_node);
                processQueue();
            } else {
                console.log(`[RunningNode] ⊘ Skipping enqueue, already showing or pending '${current_node}'`);
            }
        } else if (current_node === null || current_node === undefined) {
            // Do NOT clear on null/undefined current_node.
            // Some backends emit heartbeat or partial updates without node id between steps.
            // Keep the previous running node to avoid flicker.
            console.log('[RunningNode] ⏸ Received update without current_node; preserving previous running node');
        }

        // Handle terminal statuses
        if (status === 'completed' || status === 'failed') {
            // Mark as completed and let the queue drain naturally to honor MIN_VISIBLE_MS per node
            q.completed = true;
            q.endStatus = status === 'failed' ? 'failed' : 'completed';
            console.log(`[RunningNode] ◷ Workflow ${status}, allowing queue to drain before clear`);
            processQueue();
        }
        // Handle cancel events by clearing overlays and running icon immediately
        if (status === 'canceled' || status === 'cancelled') {
            try { useNodeStatusStore.getState().clear(); } catch {}
            if (q.t) { try { clearTimeout(q.t); } catch {} q.t = null; }
            if (q.clearT) { try { clearTimeout(q.clearT); } catch {} q.clearT = null; }
            q.queue.length = 0; q.showing = null; q.shownAt = 0; q.completed = false; q.endStatus = null;
            const rs = useRunningNodeStore.getState();
            if (rs.runningNodeId !== null) rs.setRunningNodeId(null);
            console.log('[RunningNode] ◼ Run canceled, cleared running state and overlays');
        }

        // Capture runtime state for the current node (if provided)
        try {
            if (current_node) {
                // Some backends send nodeState as { nodeState: {...} }, normalize it
                const payload = nodeState ?? {};
                const normalized = payload && typeof payload === 'object' && 'nodeState' in payload
                    ? (payload as any).nodeState
                    : payload;
                try { console.info('[NodeRuntime] update', { node: current_node, status, normalized }); } catch {}
                useRuntimeStateStore.getState().setNodeRuntimeState(current_node, normalized, status);
            }
        } catch (e) {
            // non-fatal
            logger.warn('updateSkillRunStat: failed to capture runtime state', e as any);
        }

        eventBus.emit('chat:latestSkillRunStat', request.params);
        return { success: true };
    }

    async updateTasksStat(request: IPCRequest): Promise<{ success: boolean }> {
        // logger.info('Received updateTasksStat request:', request.params);
        eventBus.emit('chat:newMessage', request.params);
        return { success: true };
    }

    async updateScreens(request: IPCRequest): Promise<{ success: boolean }> {
        logger.info('Received update_screens request:', request.params);
        
        try {
            const screensData = request.params as any;
            
            // Update the avatar scene store with the new screens data
            if (screensData && screensData.agents) {
                const sceneStore = useAvatarSceneStore.getState();
                
                // Process each agent's scenes
                Object.entries(screensData.agents).forEach(([agentId, agentData]: [string, any]) => {
                    if (agentData && agentData.scenes) {
                        sceneStore.setAgentScenes(agentId, agentData.scenes);
                    }
                });
                
                logger.info(`Updated screens for ${Object.keys(screensData.agents).length} agents`);
            }
            
            return { success: true };
        } catch (error) {
            logger.error('Error updating screens:', error);
            throw new Error(`Failed to update screens: ${error instanceof Error ? error.message : 'Unknown error'}`);
        }
    }

}


export const getHandlers = () => {
    const ipcHandlers = new IPCHandlers();
    return ipcHandlers.getHandlers();
};