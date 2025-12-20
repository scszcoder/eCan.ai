/**
 * Testing utilities and example usage for the event-driven avatar scene system
 */

import { AvatarEventManager } from '../services/avatarEventManager';
import { AvatarSceneOrchestrator } from '../services/avatarSceneOrchestrator';
import { useAvatarSceneStore } from '../stores/avatarSceneStore';
import { Scene, SceneClip, SceneEventType, ScenePriority } from '../types/avatarScene';

/**
 * Example scene data for testing the avatar scene system
 */
export const createExampleScenes = (): Scene[] => {
  return [
    {
      id: 'thinking-scene',
      name: 'Thinking Animation',
      clips: [
        {
          id: 'thinking-clip-1',
          mediaUrl: '/assets/avatars/thinking-1.gif',
          caption: 'Thinking deeply...',
          duration: 3000,
          triggers: ['thought-change', 'timer'],
          priority: 'medium',
          repeat: 2
        },
        {
          id: 'thinking-clip-2',
          mediaUrl: '/assets/avatars/thinking-2.gif',
          caption: 'Processing information...',
          duration: 2500,
          triggers: ['thought-change'],
          priority: 'medium',
          repeat: 1
        }
      ]
    },
    {
      id: 'action-scene',
      name: 'Action Animation',
      clips: [
        {
          id: 'action-clip-1',
          mediaUrl: '/assets/avatars/working.webm',
          caption: 'Working on task...',
          duration: 4000,
          triggers: ['action', 'status-change'],
          priority: 'high',
          repeat: 1
        }
      ]
    },
    {
      id: 'error-scene',
      name: 'Error Animation',
      clips: [
        {
          id: 'error-clip-1',
          mediaUrl: '/assets/avatars/error.gif',
          caption: 'Oops! Something went wrong',
          duration: 2000,
          triggers: ['error'],
          priority: 'high',
          repeat: 1
        }
      ]
    },
    {
      id: 'idle-scene',
      name: 'Idle Animation',
      clips: [
        {
          id: 'idle-clip-1',
          mediaUrl: '/assets/avatars/idle-1.gif',
          caption: 'Ready to help',
          duration: 5000,
          triggers: ['timer'],
          priority: 'low',
          repeat: -1 // Infinite loop
        }
      ]
    }
  ];
};

/**
 * Test utility class for avatar scene system
 */
export class AvatarSceneTestUtils {
  private eventManager: AvatarEventManager;
  private orchestrator: AvatarSceneOrchestrator;

  constructor() {
    this.eventManager = AvatarEventManager.getInstance();
    this.orchestrator = AvatarSceneOrchestrator.getInstance();
  }

  /**
   * Initialize test data for a specific agent
   */
  initializeTestAgent(agentId: string): void {
    const scenes = createExampleScenes();
    const sceneStore = useAvatarSceneStore.getState();
    
    // Set up scenes for the agent
    sceneStore.setAgentScenes(agentId, scenes);
    
    // Initialize the agent in the orchestrator
    this.orchestrator.initializeAgent(agentId);
    
    console.log(`Test agent ${agentId} initialized with ${scenes.length} scenes`);
  }

  /**
   * Trigger various test events for an agent
   */
  triggerTestEvents(agentId: string): void {
    const events: Array<{ type: SceneEventType; delay: number; data?: any }> = [
      { type: 'timer', delay: 0 },
      { type: 'thought-change', delay: 2000, data: { context: 'Starting to think about the problem' } },
      { type: 'action', delay: 5000, data: { context: 'Beginning task execution' } },
      { type: 'status-change', delay: 8000, data: { status: 'in_progress' } },
      { type: 'error', delay: 12000, data: { error: 'Test error scenario' } },
      { type: 'timer', delay: 15000 } // Back to idle
    ];

    events.forEach(({ type, delay, data }) => {
      setTimeout(() => {
        console.log(`Triggering ${type} event for agent ${agentId}`);
        this.eventManager.emitEvent(agentId, type, data || {});
      }, delay);
    });
  }

  /**
   * Test scene priority handling
   */
  testPriorityHandling(agentId: string): void {
    // Trigger low priority event first
    this.eventManager.emitEvent(agentId, 'timer', { priority: 'low' });
    
    // Trigger high priority event after 1 second (should interrupt)
    setTimeout(() => {
      this.eventManager.emitEvent(agentId, 'error', { priority: 'high' });
    }, 1000);
    
    // Trigger medium priority event after 3 seconds
    setTimeout(() => {
      this.eventManager.emitEvent(agentId, 'thought-change', { priority: 'medium' });
    }, 3000);
  }

  /**
   * Test event subscription and unsubscription
   */
  testEventSubscription(agentId: string): () => void {
    const unsubscribe = this.eventManager.subscribe(agentId, 'action', (eventData) => {
      console.log(`Action event received for ${agentId}:`, eventData);
    });

    // Trigger test event
    setTimeout(() => {
      this.eventManager.emitEvent(agentId, 'action', { test: 'subscription test' });
    }, 1000);

    return unsubscribe;
  }

  /**
   * Test orchestrator state changes
   */
  testOrchestratorState(agentId: string): () => void {
    const unsubscribe = this.orchestrator.subscribeToAgent(agentId, (state) => {
      console.log(`Agent ${agentId} state changed:`, {
        currentClip: state.currentClip?.id,
        isPlaying: state.isPlaying,
        queueLength: state.sceneQueue.length
      });
    });

    return unsubscribe;
  }

  /**
   * Simulate a complete agent workflow
   */
  simulateAgentWorkflow(agentId: string): void {
    console.log(`Starting agent workflow simulation for ${agentId}`);
    
    // Initialize agent
    this.initializeTestAgent(agentId);
    
    // Subscribe to state changes
    const unsubscribeState = this.testOrchestratorState(agentId);
    
    // Simulate workflow events
    const workflow = [
      { event: 'timer', delay: 0, context: 'Agent starts idle' },
      { event: 'thought-change', delay: 2000, context: 'User asks a question' },
      { event: 'action', delay: 4000, context: 'Agent starts processing' },
      { event: 'status-change', delay: 7000, context: 'Agent is working' },
      { event: 'interaction', delay: 10000, context: 'Agent provides response' },
      { event: 'timer', delay: 13000, context: 'Agent returns to idle' }
    ];

    workflow.forEach(({ event, delay, context }) => {
      setTimeout(() => {
        console.log(`Workflow: ${context}`);
        this.eventManager.emitEvent(agentId, event as SceneEventType, { context });
      }, delay);
    });

    // Clean up after 20 seconds
    setTimeout(() => {
      unsubscribeState();
      console.log(`Workflow simulation completed for ${agentId}`);
    }, 20000);
  }

  /**
   * Test error handling and fallback mechanisms
   */
  testErrorHandling(agentId: string): void {
    // Initialize agent with invalid scene data
    const invalidScenes: Scene[] = [
      {
        id: 'invalid-scene',
        name: 'Invalid Scene',
        clips: [
          {
            id: 'invalid-clip',
            mediaUrl: '/assets/nonexistent.gif', // Invalid URL
            caption: 'This should fail',
            duration: 3000,
            triggers: ['timer'],
            priority: 'medium'
          }
        ]
      }
    ];

    const sceneStore = useAvatarSceneStore.getState();
    sceneStore.setAgentScenes(agentId, invalidScenes);
    
    // Try to trigger the invalid scene
    this.eventManager.emitEvent(agentId, 'timer', {});
    
    console.log('Error handling test initiated - check console for error messages');
  }

  /**
   * Get current system statistics
   */
  getSystemStats(): any {
    const sceneStore = useAvatarSceneStore.getState();
    const analytics = sceneStore.analytics;
    
    return {
      totalScenePlays: analytics.totalScenePlays,
      totalErrors: analytics.totalErrors,
      averageSceneDuration: analytics.averageSceneDuration,
      agentCount: sceneStore.agentScenes.size,
      eventManagerStats: this.eventManager.getStats?.() || 'Not available'
    };
  }
}

/**
 * Quick test function for development
 */
export const runQuickTest = (agentId: string = 'test-agent-1'): void => {
  const testUtils = new AvatarSceneTestUtils();
  
  console.log('🚀 Starting Avatar Scene System Quick Test');
  
  // Run basic functionality test
  testUtils.simulateAgentWorkflow(agentId);
  
  // Show stats after 25 seconds
  setTimeout(() => {
    const stats = testUtils.getSystemStats();
    console.log('📊 System Statistics:', stats);
  }, 25000);
};

/**
 * Example usage in a React component
 */
export const ExampleUsage = {
  // How to use in a component
  componentExample: `
    import { DynamicAgentAnimation } from '../components/DynamicAgentAnimation';
    import { AvatarEventManager } from '../services/avatarEventManager';
    
    function MyComponent({ agentId }) {
      const eventManager = AvatarEventManager.getInstance();
      
      const handleUserAction = () => {
        // Trigger an action event when user interacts
        eventManager.emitEvent(agentId, 'action', { 
          context: 'User clicked button' 
        });
      };
      
      return (
        <div>
          <DynamicAgentAnimation 
            agentId={agentId}
            onSceneStart={(clip) => console.log('Scene started:', clip.id)}
            onSceneEnd={(clip) => console.log('Scene ended:', clip.id)}
          />
          <button onClick={handleUserAction}>Trigger Action</button>
        </div>
      );
    }
  `,
  
  // How to set up scenes via IPC
  ipcExample: `
    // Python side - sending scene data
    api = IPCAPI.get_instance()
    scenes_data = {
      "agents": {
        "agent-123": {
          "scenes": [
            {
              "id": "thinking",
              "name": "Thinking Animation",
              "clips": [
                {
                  "id": "think-1",
                  "mediaUrl": "/assets/thinking.gif",
                  "caption": "Thinking...",
                  "duration": 3000,
                  "triggers": ["thought-change"],
                  "priority": "medium"
                }
              ]
            }
          ]
        }
      }
    }
    api.update_screens(scenes_data)
  `
};

export default AvatarSceneTestUtils;
