/**
 * Avatar Scene Orchestrator
 * Event-driven scene management and orchestration service
 */

import {
  SceneEvent,
  SceneClip,
  CurrentScene,
  SceneState,
  ScenePriority,
  QueuedScene,
  SceneEventType,
  SceneStateChangeCallback,
  SceneErrorHandler
} from '@/types/avatarScene';
import { useAvatarSceneStore } from '@/stores/avatarSceneStore';
import { avatarEventManager } from '@/services/avatarEventManager';
import { logger } from '@/utils/logger';

// Scene Orchestrator Class
export class AvatarSceneOrchestrator {
  private activeTimers: Map<string, number> = new Map();
  private stateChangeCallbacks: SceneStateChangeCallback[] = [];
  private errorHandlers: SceneErrorHandler[] = [];
  private isInitialized = false;

  constructor() {
    this.initialize();
  }

  /**
   * Initialize the orchestrator
   */
  private initialize(): void {
    if (this.isInitialized) return;

    // Subscribe to all scene events
    avatarEventManager.subscribe('timer', this.handleTimerEvent.bind(this));
    avatarEventManager.subscribe('action', this.handleActionEvent.bind(this));
    avatarEventManager.subscribe('thought-change', this.handleThoughtChangeEvent.bind(this));
    avatarEventManager.subscribe('error', this.handleErrorEvent.bind(this));
    avatarEventManager.subscribe('interaction', this.handleInteractionEvent.bind(this));
    avatarEventManager.subscribe('status-change', this.handleStatusChangeEvent.bind(this));
    avatarEventManager.subscribe('emotion', this.handleEmotionEvent.bind(this));
    avatarEventManager.subscribe('custom', this.handleCustomEvent.bind(this));

    this.isInitialized = true;
    logger.info('[AvatarSceneOrchestrator] Initialized');
  }

  /**
   * Handle timer events
   */
  private async handleTimerEvent(event: SceneEvent): Promise<void> {
    const { agentId, data } = event;
    const duration = data?.duration || 0;

    logger.debug(`[AvatarSceneOrchestrator] Timer event for agent ${agentId}`, { duration });

    // Find scenes that can be triggered by timer events
    const availableScenes = useAvatarSceneStore.getState().getAvailableScenes(agentId);
    const timerScenes = availableScenes.filter(scene => 
      scene.trigger_events.some(trigger => 
        trigger === 'timer' || trigger.startsWith('timer:')
      )
    );

    if (timerScenes.length > 0) {
      // Select scene based on priority and current context
      const selectedScene = this.selectBestScene(timerScenes, event);
      if (selectedScene) {
        await this.playScene(agentId, selectedScene, event);
      }
    }
  }

  /**
   * Handle action events
   */
  private async handleActionEvent(event: SceneEvent): Promise<void> {
    const { agentId, data } = event;
    const action = data?.action;

    logger.debug(`[AvatarSceneOrchestrator] Action event for agent ${agentId}`, { action });

    const availableScenes = useAvatarSceneStore.getState().getAvailableScenes(agentId);
    const actionScenes = availableScenes.filter(scene => 
      scene.trigger_events.includes('action') ||
      scene.trigger_events.includes(`action:${action}`)
    );

    if (actionScenes.length > 0) {
      const selectedScene = this.selectBestScene(actionScenes, event);
      if (selectedScene) {
        await this.playScene(agentId, selectedScene, event);
      }
    }
  }

  /**
   * Handle thought change events
   */
  private async handleThoughtChangeEvent(event: SceneEvent): Promise<void> {
    const { agentId, data } = event;
    const thought = data?.thought;

    logger.debug(`[AvatarSceneOrchestrator] Thought change event for agent ${agentId}`, { thought });

    const availableScenes = useAvatarSceneStore.getState().getAvailableScenes(agentId);
    const thoughtScenes = availableScenes.filter(scene => 
      scene.trigger_events.includes('thought-change')
    );

    if (thoughtScenes.length > 0) {
      const selectedScene = this.selectBestScene(thoughtScenes, event);
      if (selectedScene) {
        await this.playScene(agentId, selectedScene, event);
      }
    }
  }

  /**
   * Handle error events
   */
  private async handleErrorEvent(event: SceneEvent): Promise<void> {
    const { agentId, data } = event;
    const error = data?.error;

    logger.debug(`[AvatarSceneOrchestrator] Error event for agent ${agentId}`, { error });

    const availableScenes = useAvatarSceneStore.getState().getAvailableScenes(agentId);
    const errorScenes = availableScenes.filter(scene => 
      scene.trigger_events.includes('error')
    );

    if (errorScenes.length > 0) {
      const selectedScene = this.selectBestScene(errorScenes, event);
      if (selectedScene) {
        await this.playScene(agentId, selectedScene, event);
      }
    }
  }

  /**
   * Handle interaction events
   */
  private async handleInteractionEvent(event: SceneEvent): Promise<void> {
    const { agentId, data } = event;
    const interactionType = data?.interactionType;

    logger.debug(`[AvatarSceneOrchestrator] Interaction event for agent ${agentId}`, { interactionType });

    const availableScenes = useAvatarSceneStore.getState().getAvailableScenes(agentId);
    const interactionScenes = availableScenes.filter(scene => 
      scene.trigger_events.includes('interaction') ||
      scene.trigger_events.includes(`interaction:${interactionType}`)
    );

    if (interactionScenes.length > 0) {
      const selectedScene = this.selectBestScene(interactionScenes, event);
      if (selectedScene) {
        await this.playScene(agentId, selectedScene, event);
      }
    }
  }

  /**
   * Handle status change events
   */
  private async handleStatusChangeEvent(event: SceneEvent): Promise<void> {
    const { agentId, data } = event;
    const { oldStatus, newStatus } = data || {};

    logger.debug(`[AvatarSceneOrchestrator] Status change event for agent ${agentId}`, { oldStatus, newStatus });

    const availableScenes = useAvatarSceneStore.getState().getAvailableScenes(agentId);
    const statusScenes = availableScenes.filter(scene => 
      scene.trigger_events.includes('status-change') ||
      scene.trigger_events.includes(`status-change:${newStatus}`)
    );

    if (statusScenes.length > 0) {
      const selectedScene = this.selectBestScene(statusScenes, event);
      if (selectedScene) {
        await this.playScene(agentId, selectedScene, event);
      }
    }
  }

  /**
   * Handle emotion events
   */
  private async handleEmotionEvent(event: SceneEvent): Promise<void> {
    const { agentId, data } = event;
    const emotion = data?.emotion;

    logger.debug(`[AvatarSceneOrchestrator] Emotion event for agent ${agentId}`, { emotion });

    const availableScenes = useAvatarSceneStore.getState().getAvailableScenes(agentId);
    const emotionScenes = availableScenes.filter(scene => 
      scene.trigger_events.includes('emotion') ||
      scene.trigger_events.includes(`emotion:${emotion}`)
    );

    if (emotionScenes.length > 0) {
      const selectedScene = this.selectBestScene(emotionScenes, event);
      if (selectedScene) {
        await this.playScene(agentId, selectedScene, event);
      }
    }
  }

  /**
   * Handle custom events
   */
  private async handleCustomEvent(event: SceneEvent): Promise<void> {
    const { agentId, data } = event;
    const customType = data?.customType;

    logger.debug(`[AvatarSceneOrchestrator] Custom event for agent ${agentId}`, { customType });

    const availableScenes = useAvatarSceneStore.getState().getAvailableScenes(agentId);
    const customScenes = availableScenes.filter(scene => 
      scene.trigger_events.includes('custom') ||
      scene.trigger_events.includes(`custom:${customType}`)
    );

    if (customScenes.length > 0) {
      const selectedScene = this.selectBestScene(customScenes, event);
      if (selectedScene) {
        await this.playScene(agentId, selectedScene, event);
      }
    }
  }

  /**
   * Select the best scene based on priority and context
   */
  private selectBestScene(scenes: SceneClip[], event: SceneEvent): SceneClip | null {
    if (scenes.length === 0) return null;

    // Sort by priority (highest first)
    const sortedScenes = scenes.sort((a, b) => b.priority - a.priority);

    // For now, select the highest priority scene
    // In the future, we could add more sophisticated selection logic
    return sortedScenes[0];
  }

  /**
   * Play a scene for an agent
   */
  public async playScene(agentId: string, scene: SceneClip, event?: SceneEvent): Promise<void> {
    try {
      const store = useAvatarSceneStore.getState();
      
      // Check if agent is active
      let agentState = store.getAgentState(agentId);
      if (!agentState) {
        // Initialize agent state on first use
        try { store.initializeAgent(agentId); } catch {}
        agentState = store.getAgentState(agentId);
      }
      if (agentState && agentState.isActive === false) {
        logger.debug(`[AvatarSceneOrchestrator] Agent ${agentId} is not active, skipping scene`);
        return;
      }

      // Stop current scene if playing
      await this.stopCurrentScene(agentId);

      // Create current scene state
      const currentScene: CurrentScene = {
        clip: scene,
        state: SceneState.PLAYING,
        startTime: Date.now(),
        currentRepeat: 0,
        eventContext: event
      };

      // Update store
      store.setCurrentScene(agentId, currentScene);

      // Notify state change
      this.notifyStateChange(agentId, SceneState.IDLE, SceneState.PLAYING, currentScene);

      logger.info(`[AvatarSceneOrchestrator] Playing scene for agent ${agentId}`, {
        sceneLabel: scene.label,
        clip: scene.clip,
        repeats: scene.n_repeat
      });

      // Previous implementation used a timer-based playback loop (duration per repeat).
      // We now rely on the media element's natural end. The rendering component should
      // call onMediaEnded(agentId) when the media finishes one cycle.
      // Nothing else to do here.

    } catch (error) {
      logger.error(`[AvatarSceneOrchestrator] Error playing scene for agent ${agentId}`, error);
      this.handleSceneError(agentId, error as Error, scene, event);
    }
  }

  /**
   * Handle scene playback and repeats
   */
  // Deprecated timer-based playback. We keep the method for backward compatibility but do nothing.
  private async handleScenePlayback(agentId: string, currentScene: CurrentScene): Promise<void> {
    // No-op: playback progression is now driven by onMediaEnded()
    // Keep a minimal analytics record for visibility
    const store = useAvatarSceneStore.getState();
    try { store.recordScenePlay(agentId, currentScene.clip.label, currentScene.clip.duration || 0); } catch {}
  }

  /**
   * Media element should call this when a scene's media finishes naturally
   */
  public async onMediaEnded(agentId: string): Promise<void> {
    const store = useAvatarSceneStore.getState();
    const currentScene = store.getCurrentScene(agentId);
    if (!currentScene) return;

    try {
      logger.info(`[AvatarSceneOrchestrator] onMediaEnded for agent ${agentId}`, {
        sceneLabel: currentScene.clip.label,
        currentRepeat: currentScene.currentRepeat,
        repeats: currentScene.clip.n_repeat,
        state: currentScene.state
      });
      // Increment repeat count
      currentScene.currentRepeat++;
      const { clip } = currentScene;

      if (currentScene.currentRepeat < clip.n_repeat) {
        // Continue repeating: refresh startTime to hint UI to replay
        logger.debug(`[AvatarSceneOrchestrator] Natural end, repeating ${clip.label} (${currentScene.currentRepeat}/${clip.n_repeat})`);
        currentScene.startTime = Date.now();
        currentScene.state = SceneState.PLAYING;
        store.setCurrentScene(agentId, currentScene);
        // Optional: notify state change as PLAYING→PLAYING for observers
        this.notifyStateChange(agentId, SceneState.PLAYING, SceneState.PLAYING, currentScene);
      } else {
        // Completed all repeats
        await this.completeScene(agentId, currentScene);
      }
    } catch (error) {
      logger.error(`[AvatarSceneOrchestrator] Error handling media end for agent ${agentId}`, error);
      this.handleSceneError(agentId, error as Error, currentScene.clip);
    }
  }

  /**
   * Complete a scene and return to default
   */
  private async completeScene(agentId: string, currentScene: CurrentScene): Promise<void> {
    const store = useAvatarSceneStore.getState();
    
    // Clear timer
    this.clearTimer(agentId);

    // Update scene state
    currentScene.state = SceneState.COMPLETED;
    store.setCurrentScene(agentId, currentScene);

    // Notify state change
    this.notifyStateChange(agentId, SceneState.PLAYING, SceneState.COMPLETED, currentScene);

    logger.info(`[AvatarSceneOrchestrator] Scene completed for agent ${agentId}`, {
      sceneLabel: currentScene.clip.label
    });

    // Return to default scene immediately to ensure UI reverts
    this.returnToDefault(agentId);
  }

  /**
   * Return agent to default scene
   */
  public returnToDefault(agentId: string): void {
    const store = useAvatarSceneStore.getState();
    const agentState = store.getAgentState(agentId);

    if (!agentState) return;

    // Clear current scene
    store.setCurrentScene(agentId, undefined);

    // Notify state change
    this.notifyStateChange(agentId, SceneState.COMPLETED, SceneState.IDLE);

    logger.info(`[AvatarSceneOrchestrator] Agent ${agentId} returned to default`);
  }

  /**
   * Stop current scene for an agent
   */
  public async stopCurrentScene(agentId: string): Promise<void> {
    const store = useAvatarSceneStore.getState();
    const currentScene = store.getCurrentScene(agentId);

    if (currentScene && currentScene.state === SceneState.PLAYING) {
      // Clear timer
      this.clearTimer(agentId);

      // Update state
      currentScene.state = SceneState.COMPLETED;
      store.setCurrentScene(agentId, currentScene);

      // Notify state change
      this.notifyStateChange(agentId, SceneState.PLAYING, SceneState.COMPLETED, currentScene);

      logger.debug(`[AvatarSceneOrchestrator] Stopped current scene for agent ${agentId}`);
    }
  }

  /**
   * Clear timer for an agent
   */
  private clearTimer(agentId: string): void {
    const timerId = this.activeTimers.get(agentId);
    if (timerId) {
      clearTimeout(timerId);
      this.activeTimers.delete(agentId);
    }
  }

  /**
   * Handle scene errors
   */
  private handleSceneError(agentId: string, error: Error, scene?: SceneClip, event?: SceneEvent): void {
    const store = useAvatarSceneStore.getState();
    
    // Record error in analytics
    if (scene) {
      store.recordSceneError(agentId, scene.label);
    }

    // Clear any active timers
    this.clearTimer(agentId);

    // Return to default
    this.returnToDefault(agentId);

    // Notify error handlers
    this.errorHandlers.forEach(handler => {
      try {
        handler(agentId, error, scene, event);
      } catch (handlerError) {
        logger.error('[AvatarSceneOrchestrator] Error in error handler', handlerError);
      }
    });

    logger.error(`[AvatarSceneOrchestrator] Scene error for agent ${agentId}`, {
      error: error.message,
      sceneLabel: scene?.label
    });
  }

  /**
   * Notify state change callbacks
   */
  private notifyStateChange(
    agentId: string, 
    oldState: SceneState, 
    newState: SceneState, 
    scene?: CurrentScene
  ): void {
    this.stateChangeCallbacks.forEach(callback => {
      try {
        callback(agentId, oldState, newState, scene);
      } catch (error) {
        logger.error('[AvatarSceneOrchestrator] Error in state change callback', error);
      }
    });
  }

  /**
   * Add state change callback
   */
  public onStateChange(callback: SceneStateChangeCallback): void {
    this.stateChangeCallbacks.push(callback);
  }

  /**
   * Add error handler
   */
  public onError(handler: SceneErrorHandler): void {
    this.errorHandlers.push(handler);
  }

  /**
   * Get current media URL for an agent from scene
   */
  public getCurrentMediaUrl(agentId: string): string {
    const store = useAvatarSceneStore.getState();
    const currentScene = store.getCurrentScene(agentId);

    if (currentScene && currentScene.state === SceneState.PLAYING) {
      return currentScene.clip.clip;
    }

    // Return empty string if no scene is playing (avatar should use backend-provided avatar)
    return '';
  }

  /**
   * Get current captions for an agent
   */
  public getCurrentCaptions(agentId: string): string[] {
    const store = useAvatarSceneStore.getState();
    const currentScene = store.getCurrentScene(agentId);

    if (currentScene && currentScene.state === SceneState.PLAYING) {
      return currentScene.clip.captions;
    }

    return [];
  }

  /**
   * Cleanup resources
   */
  public cleanup(): void {
    // Clear all active timers
    for (const timerId of this.activeTimers.values()) {
      clearTimeout(timerId);
    }
    this.activeTimers.clear();

    // Clear callbacks
    this.stateChangeCallbacks.length = 0;
    this.errorHandlers.length = 0;

    logger.info('[AvatarSceneOrchestrator] Cleaned up resources');
  }
}

// Global instance
export const avatarSceneOrchestrator = new AvatarSceneOrchestrator();
