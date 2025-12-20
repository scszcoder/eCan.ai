/**
 * Avatar Scene Management Types
 * Defines interfaces for event-driven avatar scene system
 */

// Scene Event Types
export type SceneEventType = 
  | 'timer'           // Time-based transitions
  | 'action'          // Agent performs an action
  | 'thought-change'  // Agent's internal state changes
  | 'error'           // Error states or failures
  | 'interaction'     // User interactions or messages
  | 'status-change'   // Agent status updates (idle, busy, offline)
  | 'emotion'         // Emotional state changes
  | 'custom';         // Custom application events

// Scene Priority Levels
export enum ScenePriority {
  LOW = 1,
  NORMAL = 2,
  HIGH = 3,
  URGENT = 4,
  CRITICAL = 5
}

// Scene State
export enum SceneState {
  IDLE = 'idle',
  QUEUED = 'queued',
  PLAYING = 'playing',
  PAUSED = 'paused',
  COMPLETED = 'completed',
  ERROR = 'error'
}

// Individual Scene Clip Configuration
export interface SceneClip {
  clip: string;                    // Path to video/image file
  n_repeat: number;               // Number of times to repeat
  captions: string[];             // Text captions to display
  label: string;                  // Scene identifier/label
  trigger_events: string[];       // Events that can trigger this scene
  priority: ScenePriority;        // Scene priority level
  fallback_scene?: string;        // Fallback scene if this fails
  duration?: number;              // Optional duration override (ms)
  metadata?: Record<string, any>; // Additional scene metadata
}

// Scene Event Data
export interface SceneEvent {
  type: SceneEventType;
  agentId: string;
  data?: any;
  timestamp: number;
  priority: ScenePriority;
  eventId: string;
  source?: string;                // Event source identifier
}

// Current Scene State for an Agent
export interface CurrentScene {
  clip: SceneClip;
  state: SceneState;
  startTime: number;
  currentRepeat: number;
  eventContext?: SceneEvent;
  timerId?: number;
}

// Scene Configuration for Multiple Agents
export interface ScenesData {
  [agentId: string]: SceneClip[];
}

// Scene Queue Item
export interface QueuedScene {
  clip: SceneClip;
  event: SceneEvent;
  queuedAt: number;
}

// Agent Scene State
export interface AgentSceneState {
  agentId: string;
  availableScenes: SceneClip[];
  currentScene?: CurrentScene;
  sceneQueue: QueuedScene[];
  defaultScene?: string;
  isActive: boolean;
}

// Scene Manager Configuration
export interface SceneManagerConfig {
  maxQueueSize: number;
  defaultFallbackScene: string;
  enableDebugLogging: boolean;
  eventTimeout: number;           // Timeout for event processing (ms)
  sceneTransitionDelay: number;   // Delay between scene transitions (ms)
}

// Scene Event Handler
export type SceneEventHandler = (event: SceneEvent) => void;

// Scene State Change Callback
export type SceneStateChangeCallback = (
  agentId: string, 
  oldState: SceneState, 
  newState: SceneState,
  scene?: CurrentScene
) => void;

// Scene Error Handler
export type SceneErrorHandler = (
  agentId: string,
  error: Error,
  scene?: SceneClip,
  event?: SceneEvent
) => void;

// Event Subscription
export interface EventSubscription {
  eventType: SceneEventType;
  agentId?: string;               // If undefined, subscribes to all agents
  handler: SceneEventHandler;
  priority: ScenePriority;
  subscriptionId: string;
}

// Scene Validation Result
export interface SceneValidationResult {
  isValid: boolean;
  errors: string[];
  warnings: string[];
}

// Scene Analytics Data
export interface SceneAnalytics {
  agentId: string;
  sceneLabel: string;
  playCount: number;
  totalDuration: number;
  averageDuration: number;
  lastPlayed: number;
  errorCount: number;
}
