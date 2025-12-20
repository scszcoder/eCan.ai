/**
 * Avatar Scene Store
 * Zustand store for managing dynamic avatar scenes state and event subscriptions
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import {
  SceneClip,
  CurrentScene,
  AgentSceneState,
  ScenesData,
  QueuedScene,
  SceneManagerConfig,
  SceneAnalytics
} from '@/types/avatarScene';
import { logger } from '@/utils/logger';

// Store State Interface
interface AvatarSceneStoreState {
  // Agent scene states
  agentScenes: Map<string, AgentSceneState>;
  
  // Global configuration
  config: SceneManagerConfig;
  
  // Analytics data
  analytics: Map<string, SceneAnalytics>;
  
  // Store actions
  setAgentScenes: (agentId: string, scenes: SceneClip[]) => void;
  updateScenesData: (scenesData: ScenesData) => void;
  setCurrentScene: (agentId: string, scene: CurrentScene | undefined) => void;
  addToQueue: (agentId: string, queuedScene: QueuedScene) => void;
  removeFromQueue: (agentId: string, index: number) => void;
  clearQueue: (agentId: string) => void;
  setAgentActive: (agentId: string, isActive: boolean) => void;
  setDefaultScene: (agentId: string, sceneLabel: string) => void;
  
  // Scene management
  getAgentState: (agentId: string) => AgentSceneState | undefined;
  getCurrentScene: (agentId: string) => CurrentScene | undefined;
  getAvailableScenes: (agentId: string) => SceneClip[];
  getSceneByLabel: (agentId: string, label: string) => SceneClip | undefined;
  getQueuedScenes: (agentId: string) => QueuedScene[];
  
  // Configuration
  updateConfig: (config: Partial<SceneManagerConfig>) => void;
  
  // Analytics
  recordScenePlay: (agentId: string, sceneLabel: string, duration: number) => void;
  recordSceneError: (agentId: string, sceneLabel: string) => void;
  getAnalytics: (agentId: string) => SceneAnalytics | undefined;
  
  // Utility
  initializeAgent: (agentId: string) => void;
  removeAgent: (agentId: string) => void;
  getAllActiveAgents: () => string[];
  getDebugInfo: () => any;
}

// Default configuration
const defaultConfig: SceneManagerConfig = {
  maxQueueSize: 10,
  defaultFallbackScene: 'default_idle',
  enableDebugLogging: true,
  eventTimeout: 5000,
  sceneTransitionDelay: 100
};

// Create the store
export const useAvatarSceneStore = create<AvatarSceneStoreState>()(
  persist(
    (set, get) => ({
      // Initial state
      agentScenes: new Map(),
      config: defaultConfig,
      analytics: new Map(),

      // Set scenes for an agent
      setAgentScenes: (agentId: string, scenes: SceneClip[]) => {
        set((state) => {
          const newAgentScenes = new Map(state.agentScenes);
          const existingState = newAgentScenes.get(agentId);
          
          const agentState: AgentSceneState = {
            agentId,
            availableScenes: scenes,
            currentScene: existingState?.currentScene,
            sceneQueue: existingState?.sceneQueue || [],
            defaultScene: existingState?.defaultScene,
            isActive: existingState?.isActive ?? true
          };
          
          newAgentScenes.set(agentId, agentState);
          
          logger.debug(`[AvatarSceneStore] Set scenes for agent ${agentId}`, {
            sceneCount: scenes.length,
            sceneLabels: scenes.map(s => s.label)
          });
          
          return { agentScenes: newAgentScenes };
        });
      },

      // Update scenes data for multiple agents
      updateScenesData: (scenesData: ScenesData) => {
        set((state) => {
          const newAgentScenes = new Map(state.agentScenes);
          
          Object.entries(scenesData).forEach(([agentId, scenes]) => {
            const existingState = newAgentScenes.get(agentId);
            
            const agentState: AgentSceneState = {
              agentId,
              availableScenes: scenes,
              currentScene: existingState?.currentScene,
              sceneQueue: existingState?.sceneQueue || [],
              defaultScene: existingState?.defaultScene,
              isActive: existingState?.isActive ?? true
            };
            
            newAgentScenes.set(agentId, agentState);
          });
          
          logger.info(`[AvatarSceneStore] Updated scenes for ${Object.keys(scenesData).length} agents`);
          
          return { agentScenes: newAgentScenes };
        });
      },

      // Set current scene for an agent
      setCurrentScene: (agentId: string, scene: CurrentScene | undefined) => {
        set((state) => {
          const newAgentScenes = new Map(state.agentScenes);
          const agentState = newAgentScenes.get(agentId);
          
          if (agentState) {
            const prev = agentState.currentScene;
            agentState.currentScene = scene;
            newAgentScenes.set(agentId, agentState);
            
            if (!scene && prev) {
              logger.info(`[AvatarSceneStore] Cleared current scene for agent ${agentId}`, {
                prevLabel: prev.clip.label
              });
            } else {
              logger.debug(`[AvatarSceneStore] Set current scene for agent ${agentId}`, {
                sceneLabel: scene?.clip.label,
                state: scene?.state
              });
            }
          }
          
          return { agentScenes: newAgentScenes };
        });
      },

      // Add scene to queue
      addToQueue: (agentId: string, queuedScene: QueuedScene) => {
        set((state) => {
          const newAgentScenes = new Map(state.agentScenes);
          const agentState = newAgentScenes.get(agentId);
          
          if (agentState) {
            // Check queue size limit
            if (agentState.sceneQueue.length >= state.config.maxQueueSize) {
              logger.warn(`[AvatarSceneStore] Queue full for agent ${agentId}, removing oldest scene`);
              agentState.sceneQueue.shift();
            }
            
            agentState.sceneQueue.push(queuedScene);
            
            // Sort by priority
            agentState.sceneQueue.sort((a, b) => b.clip.priority - a.clip.priority);
            
            newAgentScenes.set(agentId, agentState);
            
            logger.debug(`[AvatarSceneStore] Added scene to queue for agent ${agentId}`, {
              sceneLabel: queuedScene.clip.label,
              queueSize: agentState.sceneQueue.length
            });
          }
          
          return { agentScenes: newAgentScenes };
        });
      },

      // Remove scene from queue
      removeFromQueue: (agentId: string, index: number) => {
        set((state) => {
          const newAgentScenes = new Map(state.agentScenes);
          const agentState = newAgentScenes.get(agentId);
          
          if (agentState && index >= 0 && index < agentState.sceneQueue.length) {
            const removedScene = agentState.sceneQueue.splice(index, 1)[0];
            newAgentScenes.set(agentId, agentState);
            
            logger.debug(`[AvatarSceneStore] Removed scene from queue for agent ${agentId}`, {
              sceneLabel: removedScene.clip.label,
              queueSize: agentState.sceneQueue.length
            });
          }
          
          return { agentScenes: newAgentScenes };
        });
      },

      // Clear queue for an agent
      clearQueue: (agentId: string) => {
        set((state) => {
          const newAgentScenes = new Map(state.agentScenes);
          const agentState = newAgentScenes.get(agentId);
          
          if (agentState) {
            agentState.sceneQueue = [];
            newAgentScenes.set(agentId, agentState);
            
            logger.debug(`[AvatarSceneStore] Cleared queue for agent ${agentId}`);
          }
          
          return { agentScenes: newAgentScenes };
        });
      },

      // Set agent active state
      setAgentActive: (agentId: string, isActive: boolean) => {
        set((state) => {
          const newAgentScenes = new Map(state.agentScenes);
          const agentState = newAgentScenes.get(agentId);
          
          if (agentState) {
            agentState.isActive = isActive;
            newAgentScenes.set(agentId, agentState);
            
            logger.debug(`[AvatarSceneStore] Set agent ${agentId} active: ${isActive}`);
          }
          
          return { agentScenes: newAgentScenes };
        });
      },

      // Set default scene for an agent
      setDefaultScene: (agentId: string, sceneLabel: string) => {
        set((state) => {
          const newAgentScenes = new Map(state.agentScenes);
          const agentState = newAgentScenes.get(agentId);
          
          if (agentState) {
            agentState.defaultScene = sceneLabel;
            newAgentScenes.set(agentId, agentState);
            
            logger.debug(`[AvatarSceneStore] Set default scene for agent ${agentId}: ${sceneLabel}`);
          }
          
          return { agentScenes: newAgentScenes };
        });
      },

      // Get agent state
      getAgentState: (agentId: string) => {
        return get().agentScenes.get(agentId);
      },

      // Get current scene
      getCurrentScene: (agentId: string) => {
        return get().agentScenes.get(agentId)?.currentScene;
      },

      // Get available scenes
      getAvailableScenes: (agentId: string) => {
        return get().agentScenes.get(agentId)?.availableScenes || [];
      },

      // Get scene by label
      getSceneByLabel: (agentId: string, label: string) => {
        const agentState = get().agentScenes.get(agentId);
        return agentState?.availableScenes.find(scene => scene.label === label);
      },

      // Get queued scenes
      getQueuedScenes: (agentId: string) => {
        return get().agentScenes.get(agentId)?.sceneQueue || [];
      },

      // Update configuration
      updateConfig: (config: Partial<SceneManagerConfig>) => {
        set((state) => ({
          config: { ...state.config, ...config }
        }));
        
        logger.debug('[AvatarSceneStore] Updated configuration', config);
      },

      // Record scene play for analytics
      recordScenePlay: (agentId: string, sceneLabel: string, duration: number) => {
        set((state) => {
          const newAnalytics = new Map(state.analytics);
          const key = `${agentId}:${sceneLabel}`;
          const existing = newAnalytics.get(key);
          
          const analytics: SceneAnalytics = {
            agentId,
            sceneLabel,
            playCount: (existing?.playCount || 0) + 1,
            totalDuration: (existing?.totalDuration || 0) + duration,
            averageDuration: 0, // Will be calculated below
            lastPlayed: Date.now(),
            errorCount: existing?.errorCount || 0
          };
          
          analytics.averageDuration = analytics.totalDuration / analytics.playCount;
          newAnalytics.set(key, analytics);
          
          return { analytics: newAnalytics };
        });
      },

      // Record scene error for analytics
      recordSceneError: (agentId: string, sceneLabel: string) => {
        set((state) => {
          const newAnalytics = new Map(state.analytics);
          const key = `${agentId}:${sceneLabel}`;
          const existing = newAnalytics.get(key);
          
          const analytics: SceneAnalytics = {
            agentId,
            sceneLabel,
            playCount: existing?.playCount || 0,
            totalDuration: existing?.totalDuration || 0,
            averageDuration: existing?.averageDuration || 0,
            lastPlayed: existing?.lastPlayed || Date.now(),
            errorCount: (existing?.errorCount || 0) + 1
          };
          
          newAnalytics.set(key, analytics);
          
          return { analytics: newAnalytics };
        });
      },

      // Get analytics for an agent/scene
      getAnalytics: (agentId: string) => {
        const analytics = get().analytics;
        const results: SceneAnalytics[] = [];
        
        for (const [key, data] of analytics.entries()) {
          if (key.startsWith(`${agentId}:`)) {
            results.push(data);
          }
        }
        
        return results.length > 0 ? results[0] : undefined;
      },

      // Initialize agent
      initializeAgent: (agentId: string) => {
        set((state) => {
          const newAgentScenes = new Map(state.agentScenes);
          
          if (!newAgentScenes.has(agentId)) {
            const agentState: AgentSceneState = {
              agentId,
              availableScenes: [],
              sceneQueue: [],
              isActive: true
            };
            
            newAgentScenes.set(agentId, agentState);
            
            logger.debug(`[AvatarSceneStore] Initialized agent ${agentId}`);
          }
          
          return { agentScenes: newAgentScenes };
        });
      },

      // Remove agent
      removeAgent: (agentId: string) => {
        set((state) => {
          const newAgentScenes = new Map(state.agentScenes);
          const newAnalytics = new Map(state.analytics);
          
          newAgentScenes.delete(agentId);
          
          // Remove analytics for this agent
          for (const key of newAnalytics.keys()) {
            if (key.startsWith(`${agentId}:`)) {
              newAnalytics.delete(key);
            }
          }
          
          logger.debug(`[AvatarSceneStore] Removed agent ${agentId}`);
          
          return { 
            agentScenes: newAgentScenes,
            analytics: newAnalytics
          };
        });
      },

      // Get all active agents
      getAllActiveAgents: () => {
        const agentScenes = get().agentScenes;
        const activeAgents: string[] = [];
        
        for (const [agentId, state] of agentScenes.entries()) {
          if (state.isActive) {
            activeAgents.push(agentId);
          }
        }
        
        return activeAgents;
      },

      // Get debug info
      getDebugInfo: () => {
        const state = get();
        return {
          agentCount: state.agentScenes.size,
          activeAgentCount: state.getAllActiveAgents().length,
          totalQueuedScenes: Array.from(state.agentScenes.values())
            .reduce((sum, agent) => sum + agent.sceneQueue.length, 0),
          config: state.config,
          analyticsCount: state.analytics.size
        };
      }
    }),
    {
      name: 'avatar-scene-storage',
      // Only persist configuration and analytics, not runtime state
      partialize: (state) => ({
        config: state.config,
        analytics: state.analytics
      }),
      // Custom storage with Map serialization support
      storage: {
        getItem: (name) => {
          const str = localStorage.getItem(name);
          if (!str) return null;
          const parsed = JSON.parse(str);
          return {
            state: {
              ...parsed.state,
              analytics: new Map(parsed.state.analytics || [])
            }
          };
        },
        setItem: (name, value) => {
          const serialized = JSON.stringify({
            state: {
              ...value.state,
              analytics: Array.from(value.state.analytics.entries())
            }
          });
          localStorage.setItem(name, serialized);
        },
        removeItem: (name) => localStorage.removeItem(name)
      }
    }
  )
);

export default useAvatarSceneStore;
