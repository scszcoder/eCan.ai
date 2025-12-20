// 统一ExportAll store

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
export { useContextStore } from './contextStore';
export { useWarehouseStore } from './warehouseStore';
export { useProductStore } from './productStore';
export { usePromptStore } from './promptStore';

// === Tool和Service ===
export { storeSyncManager } from './sync/syncManager';

// === BaseType ===
export type {
  BaseResource,
  BaseStoreState,
  ResourceAPI,
  StoreOptions,
  APIResponse,
  CACHE_DURATION,
} from './base/types';

// === 领域Type ===
// ExportType和枚举（枚举Need作为ValueExport）
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

// ExportDataType
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