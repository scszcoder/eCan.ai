# 类型管理说明

## 概述

本项目采用模块化的类型管理方式，将所有类型定义按功能拆分到不同的文件中，便于维护和扩展。

## 目录结构

```
src/types/
├── README.md         # 类型管理说明文档
├── index.ts          # 统一导出文件
├── agent.ts          # 代理相关类型
├── skill.ts          # 技能相关类型
├── tool.ts           # 工具相关类型
├── task.ts           # 任务相关类型
├── vehicle.ts        # 车辆相关类型
├── settings.ts       # 设置相关类型
└── system.ts         # 系统数据类型和通用类型
```

## 类型定义

### 1. 代理类型 (agent.ts)

```typescript
// 代理卡片信息
export interface AgentCard {
  id: string;
  name: string;
  description: string;
  version: string;
  capabilities: {
    streaming: boolean;
  };
}

// 代理组织关系
export interface AgentOrg {
  org_id: string;
  org_name: string;
  role: string;
}

// 完整代理信息
export interface Agent {
  card: AgentCard;
  org: AgentOrg;
}
```

### 2. 技能类型 (skill.ts)

```typescript
// 技能工作流
export interface SkillWorkflow {
  // 工作流相关字段
}

// 技能配置
export interface SkillConfig {
  // 配置相关字段
}

// 技能UI信息
export interface SkillUI {
  // UI相关字段
}

// 完整技能信息
export interface Skill {
  id: string;
  name: string;
  description: string;
  level: string;
  version: string;
  workflow: SkillWorkflow;
  config: SkillConfig;
  ui: SkillUI;
}
```

### 3. 工具类型 (tool.ts)

```typescript
// 工具信息
export interface Tool {
  name: string;
  description: string;
  input_mode: string;
}
```

### 4. 任务类型 (task.ts)

```typescript
// 任务调度信息
export interface TaskSchedule {
  // 调度相关字段
}

// 任务状态
export interface TaskState {
  top: string;
  // 其他状态字段
}

// 完整任务信息
export interface Task {
  id: string;
  skill: string;
  trigger: string;
  priority: string;
  schedule: TaskSchedule;
  state: TaskState;
}
```

### 5. 车辆类型 (vehicle.ts)

```typescript
// 车辆功能
export interface VehicleFunction {
  // 功能相关字段
}

// 完整车辆信息
export interface Vehicle {
  vid: number;
  name: string;
  ip: string;
  os: string;
  status: string;
  last_update_time: string;
  functions: VehicleFunction[];
}
```

### 6. 设置类型 (settings.ts)

```typescript
// 系统设置
export interface Settings {
  debug_mode: boolean;
  default_wifi: string;
  schedule_engine: string;
  schedule_mode: string;
}
```

### 7. 系统类型 (system.ts)

```typescript
// 知识库信息
export interface Knowledge {
  [key: string]: any;
}

// 聊天记录信息
export interface Chat {
  [key: string]: any;
}

// 系统完整数据结构
export interface SystemData {
  token: string;
  agents: Agent[];
  skills: Skill[];
  tools: Tool[];
  tasks: Task[];
  vehicles: Vehicle[];
  settings: Settings;
  knowledges: Knowledge;
  chats: Chat;
}
```

## 使用方式

### 1. 导入单个类型

```typescript
import type { Agent } from './agent';
import type { Skill } from './skill';
import type { Task } from './task';
```

### 2. 导入多个类型

```typescript
import type { 
  Agent, 
  Skill, 
  Tool, 
  Task, 
  Vehicle, 
  Settings 
} from './index';
```

### 3. 导入系统数据类型

```typescript
import type { SystemData } from './system';
```

### 4. 在组件中使用

```typescript
import React from 'react';
import type { Agent, Skill } from '../types';

interface MyComponentProps {
  agents: Agent[];
  skills: Skill[];
}

const MyComponent: React.FC<MyComponentProps> = ({ agents, skills }) => {
  return (
    <div>
      <h2>代理数量: {agents.length}</h2>
      <h2>技能数量: {skills.length}</h2>
    </div>
  );
};
```

### 5. 在Store中使用

```typescript
import { create } from 'zustand';
import type { SystemData, Agent, Skill } from '../types';

interface SystemState {
  data: SystemData | null;
  agents: Agent[];
  skills: Skill[];
  // ... 其他状态
}

export const useSystemStore = create<SystemState>((set) => ({
  data: null,
  agents: [],
  skills: [],
  // ... 实现
}));
```

## 类型扩展

### 添加新的类型文件

1. 在 `src/types/` 目录下创建新的类型文件
2. 定义相关的接口
3. 在 `index.ts` 中导出新类型

```typescript
// src/types/newType.ts
export interface NewType {
  id: string;
  name: string;
  // ... 其他字段
}

// src/types/index.ts
export type { NewType } from './newType';
```

### 修改现有类型

1. 直接修改对应的类型文件
2. 确保所有使用该类型的地方都兼容新定义
3. 运行类型检查确保没有错误

## 最佳实践

### 1. 类型命名

- 使用 PascalCase 命名接口
- 使用描述性的名称
- 避免使用缩写

```typescript
// ✅ 好的命名
export interface UserProfile { }
export interface ApiResponse { }

// ❌ 不好的命名
export interface UP { }
export interface APIResp { }
```

### 2. 类型组织

- 按功能模块拆分类型文件
- 相关的类型放在同一个文件中
- 使用 index.ts 统一导出

### 3. 类型安全

- 使用 `import type` 导入类型
- 避免使用 `any` 类型
- 为所有函数参数和返回值定义类型

```typescript
// ✅ 类型安全
import type { Agent } from '../types';

const processAgent = (agent: Agent): string => {
  return agent.card.name;
};

// ❌ 类型不安全
const processAgent = (agent: any): any => {
  return agent.name;
};
```

### 4. 类型复用

- 提取公共类型到 system.ts
- 使用联合类型和交叉类型
- 使用泛型提高类型复用性

```typescript
// 公共基础类型
export interface BaseEntity {
  id: string;
  name: string;
  created_at: string;
}

// 扩展基础类型
export interface Agent extends BaseEntity {
  card: AgentCard;
  org: AgentOrg;
}
```

## 相关文件

- `index.ts`: 类型统一导出
- `agent.ts`: 代理相关类型
- `skill.ts`: 技能相关类型
- `tool.ts`: 工具相关类型
- `task.ts`: 任务相关类型
- `vehicle.ts`: 车辆相关类型
- `settings.ts`: 设置相关类型
- `system.ts`: 系统数据类型
- `../stores/systemStore.ts`: 使用类型定义的store
- `../stores/SystemStore.md`: SystemStore使用说明 