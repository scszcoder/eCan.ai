/**
 * Task Domain Types
 * 任务相关的类型定义
 */

/**
 * 任务状态枚举
 */
export enum TaskStatus {
  PENDING = 'pending',
  IN_PROGRESS = 'in_progress',
  COMPLETED = 'completed',
  FAILED = 'failed',
  CANCELLED = 'cancelled',
}

/**
 * 任务优先级
 */
export enum TaskPriority {
  LOW = 'low',
  MEDIUM = 'medium',
  HIGH = 'high',
  URGENT = 'urgent',
}

/**
 * 任务类型
 */
export interface Task {
  id: string;
  sessionId?: string;
  name?: string;
  description?: string;
  status?: TaskStatus | string;
  priority?: TaskPriority | string;
  
  // Agent 和 Skill 关联
  agentId?: string;
  skillId?: string;
  skill?: string; // skill 名称
  
  // 任务状态
  state?: {
    top?: string; // 顶层状态：'ready', 'running', 'completed', 'failed'
    [key: string]: any;
  };
  
  // 元数据
  metadata?: {
    state?: {
      top?: string;
      [key: string]: any;
    };
    [key: string]: any;
  };
  
  // 任务配置
  resume_from?: string;
  trigger?: string;
  schedule?: any;
  checkpoint_nodes?: any[];
  
  // 时间戳
  createdAt?: string;
  updatedAt?: string;
  startedAt?: string;
  completedAt?: string;
  last_run_datetime?: string | null;
  already_run_flag?: boolean;
}

/**
 * 创建任务的输入类型
 */
export interface CreateTaskInput {
  name: string;
  description?: string;
  priority?: TaskPriority;
  agentId?: string;
  skillId?: string;
  metadata?: Record<string, any>;
}

/**
 * 更新任务的输入类型
 */
export interface UpdateTaskInput {
  name?: string;
  description?: string;
  status?: TaskStatus;
  priority?: TaskPriority;
  agentId?: string;
  skillId?: string;
  metadata?: Record<string, any>;
}

