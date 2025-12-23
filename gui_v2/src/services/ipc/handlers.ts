/**
 * IPC Process器
 * Implementation了与 Python Backend通信的RequestProcess器
 */
import { IPCRequest } from './types';
import { IPCWCClient } from './ipcWCClient';
import { useNodeStatusStore } from '@/modules/skill-editor/stores/node-status-store';
import { useSheetsStore } from '@/modules/skill-editor/stores/sheets-store';
import { useSkillInfoStore } from '@/modules/skill-editor/stores/skill-info-store';
import { useAgentStore } from '../../stores/agentStore';
import { useSettingsStore } from '../../stores/settingsStore';
import {
  useTaskStore,
  useSkillStore,
  useKnowledgeStore,
  useChatStore,
} from '../../stores';
import { eventBus } from '@/utils/eventBus';
import { useRunningNodeStore } from '@/modules/skill-editor/stores/running-node-store';
import { useAvatarSceneStore } from '../../stores/avatarSceneStore';
import { useRuntimeStateStore } from '@/modules/skill-editor/stores/runtime-state-store';
import { logger } from '@/utils/logger';
import { handleSendAllContexts, handleUpdateContexts } from './contextHandlers';

import { handleOnboardingRequest, type OnboardingContext } from '../onboarding/onboardingService';
import { avatarSceneOrchestrator } from '../avatarSceneOrchestrator';
import type { SceneClip } from '@/types/avatarScene';

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
        this.registerHandler('push_chat_message', this.pushChatMessage);
        this.registerHandler('update_skill_run_stat', this.updateSkillRunStat);
        this.registerHandler('update_tasks_stat', this.updateTasksStat);
        this.registerHandler('push_chat_notification', this.pushChatNotification);
        this.registerHandler('update_all', this.updateAll);
        this.registerHandler('update_screens', this.updateScreens);
        this.registerHandler('onboarding_message', this.onboardingMessage);
        // Skill editor log push
        this.registerHandler('skill_editor_log', this.pushSkillEditorLog);
        // Context panel
        this.registerHandler('send_all_contexts', handleSendAllContexts);
        this.registerHandler('update_contexts', handleUpdateContexts);

        // LightRAG streaming events
        this.registerHandler('lightrag.queryStream.chunk', this.handleLightRagChunk);
        this.registerHandler('lightrag.queryStream.done', this.handleLightRagDone);
        this.registerHandler('lightrag.queryStream.error', this.handleLightRagError);

        // Ad banner push from backend
        this.registerHandler('push_ad', this.pushAd);

        // Account info push from backend
        this.registerHandler('push_account_info', this.pushAccountInfo);
    }
    private registerHandler(method: string, handler: Handler): void {
        this.handlers[method] = handler;
    }

    getHandlers(): HandlerMap {
        return { ...this.handlers };
    }

    // LightRAG Handlers
    async handleLightRagChunk(request: IPCRequest): Promise<{ success: boolean }> {
        const params = request.params as any;
        eventBus.emit('lightrag:queryStream:chunk', params);
        return { success: true };
    }

    async handleLightRagDone(request: IPCRequest): Promise<{ success: boolean }> {
        const params = request.params as any;
        eventBus.emit('lightrag:queryStream:done', params);
        return { success: true };
    }

    async handleLightRagError(request: IPCRequest): Promise<{ success: boolean }> {
        const params = request.params as any;
        eventBus.emit('lightrag:queryStream:error', params);
        return { success: true };
    }

    /**
     * Handle onboarding message from backend
     * Standard request handler - delegates to onboarding service
     */
    async onboardingMessage(request: IPCRequest): Promise<{ success: boolean; onboardingType: string; timestamp: number }> {
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

    // async pushChatNotification(request: IPCRequest): Promise<{ success: boolean }> {
    //       try { console.log('[IPC][pushChatNotification] raw request', request); } catch {}
    //
    //     let { chatId, content, isRead, timestamp, uid } = request.params as { chatId: string, content: any, isRead: boolean, timestamp: string, uid: string };
    //     if (!chatId || !content) {
    //         throw new Error('pushChatNotification: chatId and notification are required');
    //     }
    //     // 自动Parse字符串 JSON
    //     if (typeof content === 'string') {
    //         try {
    //             content = JSON.parse(content);
    //         } catch (e) {
    //             throw new Error('pushChatNotification: content is string but not valid JSON');
    //         }
    //     }
    //     console.log("emitting chat:newNotification")
    //     eventBus.emit('chat:newNotification', { chatId, content, isRead, timestamp, uid });
    //     return { success: true };
    // }

    async pushChatNotification(request: IPCRequest): Promise<{ success: boolean }> {
      // Debug raw request
      try { console.log('[IPC][pushChatNotification] raw request', request); } catch {}

      let { chatId, content, isRead, timestamp, uid } = request.params as {
        chatId: string, content: any, isRead: boolean, timestamp: string, uid: string
      };
      if (!chatId || !content) {
        throw new Error('pushChatNotification: chatId and notification are required');
      }

      // Parse if top-level content is a string
      if (typeof content === 'string') {
        try { content = JSON.parse(content); }
        catch { throw new Error('pushChatNotification: content is string but not valid JSON'); }
      }

      // Normalize nested structure so renderer can always read content.notification.Items
      let body: any = content;
      try {
        if (body && typeof body === 'object') {
          // Some payloads are { content: { content: { ... } } }
          if (body?.content?.content?.notification) {
            body = body.content.content;
          } else if (body?.content?.notification) {
            body = body.content;
          }
        }
      } catch {}

      // Parse common stringified subfields (card/code/form/notification)
      const maybeParse = (v: any) => {
        if (typeof v !== 'string') return v;
        try { return JSON.parse(v); } catch {}
        // Fallback: attempt to convert single quotes JSON-like to valid JSON
        try { return JSON.parse(v.replace(/'/g, '"')); } catch {}
        return v;
      };
      try {
        if (body && typeof body === 'object') {
          body.card = maybeParse(body.card);
          body.code = maybeParse(body.code);
          body.form = maybeParse(body.form);
          body.notification = maybeParse(body.notification);
        }
      } catch {}

      try { console.log('emitting chat:newNotification'); } catch {}
      eventBus.emit('chat:newNotification', { chatId, content: body, isRead, timestamp, uid });
      return { success: true };
    }

    async updateSkillRunStat(request: IPCRequest): Promise<{ success: boolean }> {
        const { agentTaskId, current_node, status, nodeState, timestamp } = request.params as { agentTaskId?: string, current_node?: string, status?: string, nodeState?: any, timestamp?: number };

        // Derive node id from nodeState when current_node is empty
        const thisNodeFromState =
          nodeState?.attributes?.__this_node__?.name ||
          (request.params as any)?.currentNode ||
          undefined;

        const effectiveNode: string | undefined =
          (typeof current_node === 'string' && current_node.length > 0)
            ? current_node
            : (typeof thisNodeFromState === 'string' && thisNodeFromState.length > 0)
              ? thisNodeFromState
              : undefined;
        // Derive thread id (prefer nodeState, fallback to langgraphState)
        const threadId =
          nodeState?.attributes?.thread_id ||
          (request.params as any)?.langgraphState?.attributes?.thread_id ||
          undefined;

        // Verbose trace toggle (enable with: window.__RUN_TRACE__ = true)
        const RUN_TRACE = ((window as any).__RUN_TRACE__ === true);

        // Log every update received from backend
        // if (RUN_TRACE) console.log(`[RunningNode][IPC] Received: current_node='${current_node}', status='${status}', ts=${timestamp ?? 'n/a'}`);

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
        if (!GN.__runningNodeQueue) {
            GN.__runningNodeQueue = {
                runId: null as string | null,
                threadId: null as string | null,
                queue: [] as string[],
                showing: null as string | null,
                shownAt: 0,
                t: null as any,
                completed: false,
                clearT: null as any,
                endStatus: null as null | 'completed' | 'failed',
                pendingSet: new Set<string>(),
                recentShown: new Map<string, number>(),
                shownSet: new Set<string>(),        // <-- add this
            };
        }

        const q = GN.__runningNodeQueue as {
          runId: string | null;
          threadId: string | null;
          queue: string[];
          showing: string | null;
          shownAt: number;
          t: any;
          completed: boolean;
          clearT: any;
          endStatus: null | 'completed' | 'failed';
          pendingSet: Set<string>;
          recentShown: Map<string, number>;
          shownSet: Set<string>;
        };

        if (!q.threadId && threadId) q.threadId = threadId;

        // Reset queue if this is a new run (by agentTaskId OR threadId change)
        const newAgentRun = agentTaskId && q.runId !== agentTaskId;
        const newThreadRun = threadId && q.threadId && q.threadId !== threadId;

        if (newAgentRun || newThreadRun) {
          if (q.t) { try { clearTimeout(q.t); } catch {} }
          if (q.clearT) { try { clearTimeout(q.clearT); } catch {} }

          // In-place reset
          q.runId = agentTaskId ?? q.runId;
          q.threadId = threadId ?? null;
          q.queue.length = 0;
          q.showing = null;
          q.shownAt = 0;
          q.completed = false;
          q.endStatus = null;
          q.pendingSet = new Set<string>();
          q.recentShown = new Map<string, number>();
          q.shownSet = new Set<string>();

          try { useNodeStatusStore.getState().clear(); } catch {}
        }

        // Re-read q after potential reset
        // const qRef = (window as any).__runningNodeQueue as { runId: string | null; queue: string[]; showing: string | null; shownAt: number; t: any; completed: boolean; clearT: any; endStatus: null | 'completed' | 'failed' };
        // const now = Date.now();
        const MIN_VISIBLE_MS = 1000; // hysteresis: each node should be visible at least this long
        const MAX_STUCK_EXTRA_MS = 2000; // fail-safe: if timers get throttled, advance after this extra time

        const showNode = (nodeId: string) => {
            if (RUN_TRACE) console.log(`[RunningNode] → Show '${nodeId}'`);
            runningNodeStore.setRunningNodeId(nodeId);
            q.showing = nodeId;
            q.shownAt = Date.now();
            try { q.pendingSet?.delete(nodeId); } catch {}
            try { q.recentShown?.set(nodeId, Date.now()); } catch {}
            try { q.shownSet?.add(nodeId); } catch {}
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
                if (RUN_TRACE) console.log(`[RunningNode] ✓ Queue drained after completion, clearing after ${delay} ms`);
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

        // If backend indicates a pause/breakpoint/stall, immediately show the node for visuals
        if (
          effectiveNode &&
          (status === 'paused' || status === 'breakpoint' || status === 'stalled')
        ) {
          // Immediately mark node as visible
          showNode(effectiveNode);
          // Also set runtime state so UI sees paused status and renders orange glow
          try {
            const payload = nodeState ?? {};
            const normalized = payload && typeof payload === 'object' && 'nodeState' in payload
              ? (payload as any).nodeState
              : payload;
            useRuntimeStateStore.getState().setNodeRuntimeState(effectiveNode, normalized, 'paused');
          } catch {}
          return { success: true };
        }

        // On resume/step/continue, proactively mark runtime state as running so GIF resumes immediately
        // BUT: don't overwrite terminal states (completed/failed)
        try {
          const isRunLikeEarly = (status === 'running' || status === 'resumed' || status === 'resume' || status === 'step' || status === 'stepping' || status === 'continue' || status === 'continued');
          if (isRunLikeEarly) {
            const payload = nodeState ?? {};
            const normalized = payload && typeof payload === 'object' && 'nodeState' in payload
              ? (payload as any).nodeState
              : payload;
            if (effectiveNode) {
              const st = useRuntimeStateStore.getState();
              const prev = st.getNodeRuntimeState(effectiveNode);
              const prevIsTerminal = prev?.status === 'completed' || prev?.status === 'failed';
              if (!prevIsTerminal) {
                st.setNodeRuntimeState(effectiveNode, normalized, 'running');
              }
            } else if (((window as any).__runningNodeQueue?.showing)) {
              const cur = (window as any).__runningNodeQueue.showing as string;
              if (cur) {
                const st = useRuntimeStateStore.getState();
                const prev = st.getNodeRuntimeState(cur);
                const prevIsTerminal = prev?.status === 'completed' || prev?.status === 'failed';
                if (!prevIsTerminal) {
                  st.setNodeRuntimeState(cur, normalized, 'running');
                }
              }
            }
          }
        } catch {}

        // Update the running node if the backend provides a specific node ID.
        if (typeof effectiveNode === 'string' && effectiveNode.length > 0) {
          const nodeId = effectiveNode;
          // Fresh-start if nothing is currently showing, nothing queued, and not completed
          const isFreshStart = !q.showing && q.queue.length === 0 && !q.completed;

          // Optional (recommended): clear anti-duplication guards on fresh start
          if (isFreshStart) {
              try {
                  q.pendingSet.clear();
              } catch {
              }
              try {
                  q.recentShown.clear();
              } catch {
              }
              try {
                  q.shownSet.clear();
              } catch {
              }
          }

          // enqueue logic should use nodeId instead of current_node
          const lastQueued = q.queue.length > 0 ? q.queue[q.queue.length - 1] : null;
          const cooldownMs = 800;
          const nowTs = Date.now();
          const lastShown = q.recentShown ? (q.recentShown.get(nodeId) || 0) : 0;
          const alreadyPending = q.pendingSet ? q.pendingSet.has(nodeId) : false;
          const canEnqueue =
            nodeId !== q.showing &&
            nodeId !== lastQueued &&
            !alreadyPending &&
            ((nowTs - lastShown >= cooldownMs) || isFreshStart) &&
            (!q.shownSet?.has(nodeId) || isFreshStart);

          if (canEnqueue) {
            if (RUN_TRACE) console.log(`[RunningNode] ≈ Enqueue '${nodeId}'`);
            if (!q.showing && q.queue.length === 0 && !q.completed) {
              try { useNodeStatusStore.getState().clear(); } catch {}
            }
            q.queue.push(nodeId);
            try { q.pendingSet?.add(nodeId); } catch {}
            processQueue();
          } else {
            if (RUN_TRACE) console.log(`[RunningNode] ⊘ Skipping enqueue '${nodeId}' (dup or cooldown)`);
          }
        } else if (current_node === null || current_node === undefined) {
          if (RUN_TRACE) console.log('[RunningNode] ⏸ Received update without current_node; preserving previous running node');
        }

        if (
          !current_node &&
          effectiveNode &&
          (status === 'paused' || status === 'breakpoint' || status === 'stalled')
        ) {
          // Show immediately to render breakpoint visuals (stickman + breathing)
          showNode(effectiveNode);
          // Do not schedule draining here; wait for subsequent updates
          return { success: true };
        } else if (current_node === null || current_node === undefined) {
          if (RUN_TRACE) console.log('[RunningNode] ⏸ Received update without current_node; preserving previous running node');
        }

        // Handle terminal statuses
        if (status === 'completed' || status === 'failed') {
            // Mark as completed and let the queue drain naturally to honor MIN_VISIBLE_MS per node
            q.completed = true;
            q.endStatus = status === 'failed' ? 'failed' : 'completed';
            if (RUN_TRACE) console.log(`[RunningNode] ◷ Workflow ${status}, allowing queue to drain before clear`);
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
            if (RUN_TRACE) console.log('[RunningNode] ◼ Run canceled, cleared running state and overlays');
        }

        // Capture runtime state even if current_node is empty, using effectiveNode
        try {
          const payload = nodeState ?? {};
          const normalized = payload && typeof payload === 'object' && 'nodeState' in payload
            ? (payload as any).nodeState
            : payload;
          // Map backend status to UI runtime status
          const isPausedLike = (status === 'paused' || status === 'breakpoint' || status === 'stalled');
          const isRunLike = (
            status === 'running' || status === 'resumed' || status === 'resume' ||
            status === 'step' || status === 'stepping' || status === 'continue' || status === 'continued'
          );
          const uiStatus: 'paused' | 'running' | any = isPausedLike ? 'paused' : (isRunLike ? 'running' : (status || 'running'));

          if (effectiveNode) {
            // Prevent 'running' from overwriting terminal states ('completed' or 'failed')
            // This handles the case where LangGraph calls node_builder multiple times
            const st = useRuntimeStateStore.getState();
            const prev = st.getNodeRuntimeState(effectiveNode);
            const prevStatus = prev?.status;
            const prevIsTerminal = prevStatus === 'completed' || prevStatus === 'failed';
            
            console.log(`[NodeRuntime] node=${effectiveNode}, backend=${status}, ui=${uiStatus}, prev=${prevStatus}, terminal=${prevIsTerminal}`);
            
            if (prevIsTerminal && uiStatus === 'running') {
              // Skip: don't let a stale 'running' overwrite a terminal state
              console.log(`[NodeRuntime] SKIP: ${effectiveNode} already ${prevStatus}, ignoring ${uiStatus}`);
            } else {
              st.setNodeRuntimeState(effectiveNode, normalized, uiStatus);
            }
          } else if ((isRunLike) && q.showing) {
            // Fallback: when backend omits current_node/this_node on resume, update the currently showing node
            // Only flip to running if this node was previously paused-like to prevent UI churn
            try {
              const st = useRuntimeStateStore.getState();
              const prev = (st as any).getNodeRuntimeState?.(q.showing);
              const wasPausedLike = prev?.status === 'paused' || prev?.status === 'breakpoint' || prev?.status === 'stalled';
              if (wasPausedLike) {
                if (RUN_TRACE) console.info('[NodeRuntime] resume-fallback update', { node: q.showing, status, uiStatus, normalized });
                st.setNodeRuntimeState(q.showing, normalized, 'running');
              }
            } catch {}
          } else if (status === 'paused' && q.showing) {
            // Fallback: when backend omits current_node/this_node on pause, update the currently showing node
            try { if (RUN_TRACE) console.info('[NodeRuntime] pause-fallback update', { node: q.showing, status, normalized }); } catch {}
            useRuntimeStateStore.getState().setNodeRuntimeState(q.showing, normalized, 'paused');
          }
        } catch (e) {
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

    async pushSkillEditorLog(request: IPCRequest): Promise<{ success: boolean }>{
        try {
            const p = (request.params as any) || {};
            // Accept either { type, text } or nested { message: { type, text } }
            const payload = p.message && typeof p.message === 'object' ? p.message : p;
            const t = String(payload.type || 'log').toLowerCase();
            const text = typeof payload.text === 'string' ? payload.text : JSON.stringify(payload.text ?? payload);
            const entry = { type: t as 'log' | 'warning' | 'error', text, timestamp: Date.now() };
            eventBus.emit('skill-editor:log', entry);
            return { success: true };
        } catch (e) {
            eventBus.emit('skill-editor:log', { type: 'error', text: `malformed log payload: ${String(e)}`, timestamp: Date.now() });
            return { success: true };
        }
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
                      const scenes = agentData.scenes as SceneClip[];
                      sceneStore.setAgentScenes(agentId, scenes);

                      // Prefer an explicitly requested scene, else highest priority
                      let target: SceneClip | undefined;
                      const desiredLabel: string | undefined =
                        agentData.current?.label || agentData.play?.label || agentData.desired_label;
                      const desiredClip: string | undefined =
                        agentData.current?.clip || agentData.play?.clip;

                      if (desiredLabel) target = scenes.find(s => s.label === desiredLabel);
                      if (!target && desiredClip) target = scenes.find(s => s.clip === desiredClip);
                      if (!target && scenes.length > 0) {
                        target = [...scenes].sort((a, b) => (b.priority || 0) - (a.priority || 0))[0];
                      }

                      if (target) {
                        try {
                          avatarSceneOrchestrator.playScene(agentId, target);
                          logger.debug(`[IPC][update_screens] Started playback for agent ${agentId}`, {
                            label: target.label, repeats: target.n_repeat
                          });
                        } catch (e) {
                          logger.error(`[IPC][update_screens] Failed to start playback for agent ${agentId}`, e as any);
                        }
                      }
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

    /**
     * Toggle window fullscreen state
     */
    async windowToggleFullscreen(): Promise<boolean> {
        logger.debug('[IPC] Window toggle fullscreen called');
        const response = await IPCWCClient.getInstance().invoke('window_toggle_fullscreen', {});
        logger.debug('[IPC] Window toggle fullscreen response:', response);
        return response?.result?.is_fullscreen ?? response?.data?.is_fullscreen ?? false;
    }

    /**
     * Handle ad push from backend
     */
    async pushAd(request: IPCRequest): Promise<{ success: boolean }> {
        const params = request.params as {
            bannerText?: string;
            popupHtml?: string;
            durationMs?: number;
        };
        
        const { useAdStore } = await import('../../stores/adStore');
        const store = useAdStore.getState();
        const durationMs = params.durationMs || 60000;
        const expiresAt = Date.now() + durationMs;
        
        if (params.bannerText) {
            store.setBannerAd({
                id: `ad-banner-${Date.now()}`,
                text: params.bannerText,
                expiresAt,
            });
        }
        
        if (params.popupHtml) {
            store.setPopupAd({
                id: `ad-popup-${Date.now()}`,
                htmlContent: params.popupHtml,
                expiresAt,
            });
        }
        
        logger.info('[IPC] Ad pushed from backend', { durationMs });
        return { success: true };
    }

    /**
     * Handle account info push from backend
     */
    async pushAccountInfo(request: IPCRequest): Promise<{ success: boolean }> {
        const params = request.params as {
            accountInfo?: any;
        };
        
        if (!params.accountInfo) {
            logger.warn('[IPC] No account info in push_account_info request');
            return { success: false };
        }
        
        const { useAccountStore } = await import('../../stores/accountStore');
        const store = useAccountStore.getState();
        
        store.setAccountData(params.accountInfo);
        
        logger.info('[IPC] Account info pushed from backend');
        return { success: true };
    }

    /**
     * Get window fullscreen state
     */
    async windowGetFullscreenState(): Promise<boolean> {
        logger.debug('[IPC] Window get fullscreen state called');
        const response = await IPCWCClient.getInstance().invoke('window_get_fullscreen_state', {});
        logger.debug('[IPC] Window get fullscreen state response:', response);
        return response?.result?.is_fullscreen ?? response?.data?.is_fullscreen ?? false;
    }

}


export const getHandlers = () => {
    const ipcHandlers = new IPCHandlers();
    return ipcHandlers.getHandlers();
};