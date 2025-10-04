// 统一导出所有 store

// === 应用级 Store ===
export { useUserStore } from './userStore';
export { useAppStore } from './appStore';
export { useAppDataStore } from './appDataStore';
export { useAvatarSceneStore } from './avatarSceneStore';

// === 领域 Store (Domain Stores) ===
export { useAgentStore } from './agentStore';
export { useTaskStore } from './domain/taskStore';
export { useSkillStore } from './domain/skillStore';
export { useVehicleStore } from './domain/vehicleStore';
export { useRankStore } from './domain/rankStore';
export { useKnowledgeStore } from './domain/knowledgeStore';
export { useChatStore } from './domain/chatStore';

// === 工具和服务 ===
export { storeSyncManager } from './sync/syncManager';

// === 基础类型 ===
export type {
  BaseResource,
  BaseStoreState,
  ResourceAPI,
  StoreOptions,
  APIResponse,
  CACHE_DURATION,
} from './base/types';

// === 领域类型 ===
// 导出类型和枚举（枚举需要作为值导出）
export type { Task } from '../types/domain/task';
export { TaskStatus, TaskPriority } from '../types/domain/task';

export type { Skill } from '../types/domain/skill';
export { SkillLevel, SkillStatus } from '../types/domain/skill';

export type { Vehicle, SystemInfo } from '../types/domain/vehicle';
export { VehicleStatus, VehicleType } from '../types/domain/vehicle';

export type { Knowledge } from '../types/domain/knowledge';
export { KnowledgeType, KnowledgeStatus } from '../types/domain/knowledge';

export type { Chat, Message, Member } from '../types/domain/chat';
export { ChatType, MessageStatus, MemberStatus } from '../types/domain/chat';

// 导出数据类型
// export type {
//   Agent,
//   Skill,
//   Tool,
//   Task,
//   Vehicle,
//   Settings,
//   Knowledge,
//   Chat,
//   SystemData
// } from '../types';