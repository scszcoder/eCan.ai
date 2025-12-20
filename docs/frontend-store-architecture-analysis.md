# GUI_V2 前端 Store 架构分析与改进方案

## 📊 当前架构分析

### 1. 现有 Store 结构

```
gui_v2/src/stores/
├── index.ts                    # 统一导出
├── AppDataStoreHandler.ts      # 数据同步处理器
├── appDataStore.ts             # 全局应用数据 (混合型)
├── agentStore.ts               # Agent 专用 store ✅
├── userStore.ts                # 用户状态 (简单)
├── appStore.ts                 # 应用状态
├── skillStore.ts               # Skill 名称 (简单)
├── taskStore.ts                # Task 名称 (简单)
├── vehicleStore.ts             # Vehicle 名称 (简单)
├── toolStore.ts                # Tool 数据 ✅
├── orgStore.ts                 # 组织数据 ✅
├── settingsStore.ts            # 设置
├── knowledgeStore.ts           # 知识库
├── avatarSceneStore.ts         # Avatar 场景
├── nodeStateSchemaStore.ts     # 节点状态 schema
├── personalityStore.ts         # 个性化
├── rankStore.ts                # 等级
└── titleStore.ts               # 标题
```

### 2. 架构问题分析

#### ❌ 问题 1: Store 职责混乱

**appDataStore.ts** 是一个"大杂烩" store：
- 包含 tasks, skills, tools, vehicles, settings, chats, knowledges
- 混合了数据存储、状态管理、数据获取逻辑
- 违反单一职责原则

```typescript
// appDataStore.ts - 职责过多
export interface AppData {
  tasks: Task[];
  knowledges: Knowledge[];
  skills: Skill[];
  tools: Tool[];
  vehicles: Vehicle[];
  settings: Settings | null;
  chats: Chat[];
  isLoading: boolean;
  error: string | null;
  initialized: boolean;
  // ... 还有很多方法
}
```

#### ❌ 问题 2: Store 粒度不一致

- **agentStore.ts**: 完整的 CRUD + 数据获取 ✅ (好的示例)
- **toolStore.ts**: 只有数据获取，没有 CRUD ⚠️
- **skillStore.ts**: 只存储一个名称 ❌ (过于简单)
- **vehicleStore.ts**: 只存储一个名称 ❌ (过于简单)
- **taskStore.ts**: 文件名错误，实际是 rankStore ❌

#### ❌ 问题 3: 数据同步机制不统一

- **AppDataStoreHandler.ts**: 手动同步，需要显式调用
- **agentStore**: 自己管理数据获取和同步
- **toolStore**: 自己管理数据获取
- 没有统一的数据同步策略

#### ❌ 问题 4: 缺少标准化的 Store 模式

不同 store 的实现方式差异很大：
- 有的使用 `persist` 中间件，有的不使用
- 有的有 `loading/error` 状态，有的没有
- 有的有 `lastFetched` 缓存策略，有的没有

#### ❌ 问题 5: 类型定义分散

- Agent 类型在 `@/pages/Agents/types`
- Task 类型在 `@/pages/Tasks/types`
- 没有统一的类型定义位置

---

## ✅ 标准架构设计方案

### 1. 架构原则

1. **单一职责原则**: 每个 store 只管理一种资源
2. **统一接口**: 所有 store 遵循相同的接口规范
3. **分层设计**: 数据层、业务层、UI 层分离
4. **可组合性**: Store 之间可以相互引用和组合
5. **类型安全**: 完整的 TypeScript 类型支持

### 2. 标准 Store 结构

```typescript
// 标准 Store 接口
interface BaseStoreState<T> {
  // 数据
  items: T[];
  
  // 状态
  loading: boolean;
  error: string | null;
  lastFetched: number | null;
  
  // 基础 CRUD
  setItems: (items: T[]) => void;
  addItem: (item: T) => void;
  updateItem: (id: string, updates: Partial<T>) => void;
  removeItem: (id: string) => void;
  
  // 查询
  getItemById: (id: string) => T | null;
  
  // 数据获取
  fetchItems: (username: string) => Promise<void>;
  shouldFetch: () => boolean;
  
  // 状态管理
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  clearData: () => void;
}
```

### 3. 目录结构重构

```
gui_v2/src/
├── stores/
│   ├── index.ts                    # 统一导出
│   ├── base/
│   │   ├── createBaseStore.ts      # Store 工厂函数
│   │   ├── types.ts                # 基础类型定义
│   │   └── middleware.ts           # 通用中间件
│   ├── domain/                     # 领域 Store
│   │   ├── agentStore.ts
│   │   ├── taskStore.ts
│   │   ├── skillStore.ts
│   │   ├── vehicleStore.ts
│   │   ├── toolStore.ts
│   │   ├── orgStore.ts
│   │   ├── knowledgeStore.ts
│   │   └── chatStore.ts
│   ├── app/                        # 应用级 Store
│   │   ├── userStore.ts
│   │   ├── settingsStore.ts
│   │   └── uiStore.ts
│   └── sync/                       # 数据同步
│       ├── syncManager.ts
│       └── syncStrategies.ts
├── types/                          # 统一类型定义
│   ├── domain/
│   │   ├── agent.ts
│   │   ├── task.ts
│   │   ├── skill.ts
│   │   └── ...
│   └── api/
│       └── responses.ts
└── services/
    └── api/
        ├── agentApi.ts
        ├── taskApi.ts
        └── ...
```

### 4. 核心改进点

#### 改进 1: 创建 Store 工厂函数

```typescript
// stores/base/createBaseStore.ts
export function createResourceStore<T extends { id: string }>(
  resourceName: string,
  apiService: ResourceAPI<T>
) {
  return create<ResourceStoreState<T>>()(
    persist(
      (set, get) => ({
        items: [],
        loading: false,
        error: null,
        lastFetched: null,
        
        // 标准化的实现...
      }),
      {
        name: `${resourceName}-storage`,
        partialize: (state) => ({
          items: state.items,
          lastFetched: state.lastFetched,
        }),
      }
    )
  );
}
```

#### 改进 2: 统一数据同步管理器

```typescript
// stores/sync/syncManager.ts
export class StoreSyncManager {
  private stores: Map<string, any> = new Map();
  
  register(name: string, store: any) {
    this.stores.set(name, store);
  }
  
  async syncAll(username: string) {
    const promises = Array.from(this.stores.values()).map(
      store => store.getState().fetchItems(username)
    );
    await Promise.all(promises);
  }
  
  clearAll() {
    this.stores.forEach(store => store.getState().clearData());
  }
}
```

#### 改进 3: 类型定义集中化

```typescript
// types/domain/agent.ts
export interface Agent {
  id: string;
  card: AgentCard;
  rank: string;
  organizations: string[];
  // ...
}

export interface AgentCard {
  id: string;
  name: string;
  // ...
}
```

#### 改进 4: API 服务层分离

```typescript
// services/api/agentApi.ts
export class AgentAPI {
  async getAgents(username: string): Promise<Agent[]> {
    const api = createIPCAPI();
    const response = await api.getAgents(username);
    return response.data.agents;
  }
  
  async saveAgent(username: string, agent: Agent): Promise<void> {
    const api = createIPCAPI();
    await api.saveAgents(username, [agent]);
  }
  
  // ...
}
```

---

## 🎯 迁移计划

### Phase 1: 基础设施 (Week 1)
- [ ] 创建 `stores/base/` 目录和工厂函数
- [ ] 创建 `types/domain/` 统一类型定义
- [ ] 创建 `services/api/` API 服务层

### Phase 2: 核心 Store 重构 (Week 2-3)
- [ ] 重构 taskStore (使用标准模式)
- [ ] 重构 skillStore (使用标准模式)
- [ ] 重构 vehicleStore (使用标准模式)
- [ ] 重构 knowledgeStore (使用标准模式)
- [ ] 重构 chatStore (使用标准模式)

### Phase 3: 数据同步优化 (Week 4)
- [ ] 实现 StoreSyncManager
- [ ] 移除 AppDataStoreHandler
- [ ] 统一数据同步策略

### Phase 4: 清理和优化 (Week 5)
- [ ] 移除 appDataStore (数据已分散到各个 store)
- [ ] 更新所有组件引用
- [ ] 性能优化和测试

---

## 📝 实施细节

### 示例: 重构 taskStore

**当前状态** (taskStore.ts 实际是 rankStore):
```typescript
interface RankState {
  rankname: string | null;
  setRankname: (rankname: string) => void;
}
```

**重构后**:
```typescript
// types/domain/task.ts
export interface Task {
  id: string;
  name: string;
  description: string;
  status: TaskStatus;
  agentId: string;
  // ...
}

// stores/domain/taskStore.ts
export const useTaskStore = createResourceStore<Task>(
  'task',
  new TaskAPI()
);
```

---

## 🔍 对比总结

| 方面 | 当前架构 | 标准架构 |
|------|---------|---------|
| **职责划分** | ❌ 混乱，appDataStore 包含所有 | ✅ 清晰，每个资源独立 store |
| **代码复用** | ❌ 每个 store 重复实现 | ✅ 工厂函数统一创建 |
| **类型安全** | ⚠️ 类型分散在各处 | ✅ 统一类型定义 |
| **数据同步** | ❌ 手动同步，不统一 | ✅ 自动同步管理器 |
| **可维护性** | ❌ 低，修改困难 | ✅ 高，模式统一 |
| **可测试性** | ⚠️ 中等 | ✅ 高，依赖注入 |
| **性能** | ⚠️ 大 store 性能差 | ✅ 细粒度更新 |

---

## 🚀 立即可做的改进

1. **重命名 taskStore.ts** → rankStore.ts (修正错误)
2. **创建真正的 taskStore.ts** (参考 agentStore 模式)
3. **创建 skillStore.ts** (完整版本，不只是名称)
4. **创建 vehicleStore.ts** (完整版本，不只是名称)
5. **统一所有 store 的接口** (添加 loading/error/lastFetched)

---

## ✅ 已完成的改进

### 1. 基础设施搭建 ✅

已创建以下文件：

- ✅ `gui_v2/src/stores/base/types.ts` - 基础类型定义
- ✅ `gui_v2/src/stores/base/createBaseStore.ts` - Store 工厂函数
- ✅ `gui_v2/src/types/domain/task.ts` - Task 类型定义
- ✅ `gui_v2/src/services/api/taskApi.ts` - Task API 服务
- ✅ `gui_v2/src/stores/domain/taskStore.ts` - 标准化的 Task Store
- ✅ `gui_v2/src/stores/sync/syncManager.ts` - 数据同步管理器

### 2. 核心功能

#### Store 工厂函数

```typescript
// 使用工厂函数创建标准 store
const useTaskStore = createResourceStore<Task>(
  { name: 'task', persist: true },
  new TaskAPI()
);

// 或创建扩展 store
const useAgentStore = createExtendedResourceStore<Agent, AgentStoreExtension>(
  { name: 'agent' },
  new AgentAPI(),
  (baseState) => ({
    ...baseState,
    // 添加自定义方法
  })
);
```

#### 数据同步管理器

```typescript
// 注册 stores
storeSyncManager.register('agent', useAgentStore);
storeSyncManager.register('task', useTaskStore);

// 同步所有数据
await storeSyncManager.syncAll(username);

// 清除所有数据
storeSyncManager.clearAll();
```

---

## 📖 使用指南

### 如何创建新的 Store

#### 步骤 1: 定义类型

```typescript
// types/domain/myResource.ts
export interface MyResource {
  id: string;
  name: string;
  // ... 其他字段
}
```

#### 步骤 2: 创建 API 服务

```typescript
// services/api/myResourceApi.ts
export class MyResourceAPI implements ResourceAPI<MyResource> {
  async getAll(username: string): Promise<APIResponse<MyResource[]>> {
    // 实现获取逻辑
  }

  async create(username: string, item: MyResource): Promise<APIResponse<MyResource>> {
    // 实现创建逻辑
  }

  // ... 其他方法
}
```

#### 步骤 3: 创建 Store

```typescript
// stores/domain/myResourceStore.ts
export const useMyResourceStore = createResourceStore<MyResource>(
  {
    name: 'myResource',
    persist: true,
    cacheDuration: CACHE_DURATION.MEDIUM,
  },
  new MyResourceAPI()
);
```

#### 步骤 4: 在组件中使用

```typescript
// 在组件中使用
function MyComponent() {
  const { items, loading, error, fetchItems } = useMyResourceStore();
  const username = useUserStore(state => state.username);

  useEffect(() => {
    if (username) {
      fetchItems(username);
    }
  }, [username]);

  if (loading) return <Spin />;
  if (error) return <Alert message={error} type="error" />;

  return (
    <div>
      {items.map(item => (
        <div key={item.id}>{item.name}</div>
      ))}
    </div>
  );
}
```

### 如何迁移现有 Store

#### 示例：迁移 skillStore

**旧代码** (gui_v2/src/stores/skillStore.ts):
```typescript
interface SkillState {
  skillname: string | null;
  setSkillname: (skillname: string) => void;
}

export const useSkillStore = create<SkillState>((set) => ({
  skillname: null,
  setSkillname: (skillname) => set({ skillname }),
}));
```

**新代码** (gui_v2/src/stores/domain/skillStore.ts):
```typescript
export const useSkillStore = createResourceStore<Skill>(
  {
    name: 'skill',
    persist: true,
    cacheDuration: CACHE_DURATION.MEDIUM,
  },
  new SkillAPI()
);
```

**迁移步骤**:
1. 创建 `types/domain/skill.ts` 定义 Skill 类型
2. 创建 `services/api/skillApi.ts` 实现 API 调用
3. 使用工厂函数创建新的 skillStore
4. 更新组件中的引用
5. 删除旧的 skillStore.ts

---

## 🔧 下一步工作

### 立即执行（本周）

1. ✅ 创建基础设施（已完成）
2. ⏳ 重命名 `taskStore.ts` → `rankStore.ts`
3. ⏳ 创建完整的 `skillStore.ts`
4. ⏳ 创建完整的 `vehicleStore.ts`
5. ⏳ 在 Dashboard 中集成 syncManager

### 短期目标（2周内）

1. 迁移所有简单 store 到新架构
2. 重构 appDataStore，移除冗余数据
3. 统一所有组件的 store 使用方式
4. 添加单元测试

### 长期目标（1个月内）

1. 完全移除 appDataStore
2. 实现实时数据同步
3. 添加离线支持
4. 性能优化和监控


