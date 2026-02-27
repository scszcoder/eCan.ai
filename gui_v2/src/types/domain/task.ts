/**
 * Task Domain Types
 * Type definitions for tasks
 */

/**
 * Task status enumeration
 */
export enum TaskStatus {
  PENDING = 'pending',
  IN_PROGRESS = 'in_progress',
  COMPLETED = 'completed',
  FAILED = 'failed',
  CANCELLED = 'cancelled',
}

/**
 * Task priority
 */
export enum TaskPriority {
  LOW = 'low',
  MEDIUM = 'medium',
  HIGH = 'high',
  URGENT = 'urgent',
}

/**
 * Task execution type - where the task runs
 */
export enum TaskType {
  LOCAL = 'local',
  CLOUD = 'cloud',
  HYBRID_CLOUD = 'hybrid_cloud',
}

/**
 * Task type
 */
export interface Task {
  id: string;
  sessionId?: string;
  name?: string;
  description?: string;
  task_type?: TaskType | string;
  cloud_based?: boolean; // @deprecated Use task_type instead
  status?: TaskStatus | string;
  priority?: TaskPriority | string;
  source?: 'code' | 'ui'; // Task source: code-generated or UI-created
  
  // Agent and Skill associations
  agentId?: string;
  skillId?: string;
  skill?: string; // skill name
  
  // Task state
  state?: {
    top?: string; // Top-level state: 'ready', 'running', 'completed', 'failed'
    [key: string]: any;
  };
  
  // Metadata
  metadata?: {
    state?: {
      top?: string;
      [key: string]: any;
    };
    [key: string]: any;
  };
  
  // Task configuration
  resume_from?: string;
  trigger?: string;
  schedule?: any;
  checkpoint_nodes?: any[];
  
  // Timestamps
  createdAt?: string;
  updatedAt?: string;
  startedAt?: string;
  completedAt?: string;
  last_run_datetime?: string | null;
  already_run_flag?: boolean;
}

/**
 * Create task input type
 */
export interface CreateTaskInput {
  name: string;
  description?: string;
  task_type?: TaskType | string;
  priority?: TaskPriority;
  agentId?: string;
  skillId?: string;
  metadata?: Record<string, any>;
}

/**
 * Update task input type
 */
export interface UpdateTaskInput {
  name?: string;
  description?: string;
  task_type?: TaskType | string;
  status?: TaskStatus;
  priority?: TaskPriority;
  agentId?: string;
  skillId?: string;
  metadata?: Record<string, any>;
}

