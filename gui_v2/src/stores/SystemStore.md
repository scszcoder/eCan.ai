# SystemStore 使用说明

## 概述

`SystemStore` 是一个基于 Zustand 的状态管理store，用于管理从API获取的系统数据，包括代理、技能、工具、任务、车辆、设置等信息。

## 数据结构

### 主要数据类型

所有数据类型定义都位于 `src/types/` 目录下：

- **Agent** (`src/types/agent.ts`): 代理信息，包含卡片信息、能力、组织关系等
- **Skill** (`src/types/skill.ts`): 技能信息，包含工作流、配置、UI信息等
- **Tool** (`src/types/tool.ts`): 工具信息，包含输入模式、描述等
- **Task** (`src/types/task.ts`): 任务信息，包含调度、状态、优先级等
- **Vehicle** (`src/types/vehicle.ts`): 车辆信息，包含IP、状态、功能等
- **Settings** (`src/types/settings.ts`): 系统设置信息
- **Knowledge** (`src/types/system.ts`): 知识库信息
- **Chat** (`src/pages/Chat/types/chat.ts`): 聊天会话信息，包含消息、成员等
- **Message** (`src/pages/Chat/types/chat.ts`): 消息信息，包含内容、附件、状态等
- **Attachment** (`src/pages/Chat/types/chat.ts`): 附件信息
- **SystemData** (`src/types/system.ts`): 系统完整数据结构

### 类型导入

```typescript
// 导入单个类型
import type { Agent } from '../types/agent';
import type { Skill } from '../types/skill';

// 导入多个类型
import type { Agent, Skill, Tool, Task, Vehicle, Settings } from '../types';

// 导入系统数据类型
import type { SystemData } from '../types/system';

// 导入Chat相关类型
import type { Chat, Message, Attachment } from '../pages/Chat/types/chat';
```

## 使用方法

### 1. 基本使用

```typescript
import { useSystemStore } from '../stores/systemStore';

const MyComponent = () => {
  const { 
    agents, 
    skills, 
    tools, 
    tasks, 
    vehicles, 
    settings,
    chats,
    isLoading,
    error 
  } = useSystemStore();

  if (isLoading) {
    return <div>加载中...</div>;
  }

  if (error) {
    return <div>错误: {error}</div>;
  }

  return (
    <div>
      <h2>代理数量: {agents.length}</h2>
      <h2>技能数量: {skills.length}</h2>
      <h2>聊天会话数量: {chats.length}</h2>
      {/* 其他内容 */}
    </div>
  );
};
```

### 2. 更新数据

```typescript
const { setData, updateAgent, addSkill, addChat } = useSystemStore();

// 设置完整数据
setData(systemData);

// 更新单个代理
updateAgent('agent-id', { 
  card: { ...agent.card, name: '新名称' } 
});

// 添加新技能
addSkill(newSkill);

// 添加新聊天会话
addChat(newChat);
```

### 3. 数据操作

```typescript
const { 
  addAgent, 
  removeAgent, 
  updateSkill, 
  addChat,
  updateChat,
  removeChat,
  setLoading,
  setError 
} = useSystemStore();

// 添加代理
addAgent(newAgent);

// 删除代理
removeAgent('agent-id');

// 更新技能
updateSkill('skill-id', { name: '新技能名称' });

// 添加聊天会话
addChat(newChat);

// 更新聊天会话
updateChat(chatId, { lastMessage: '新消息' });

// 删除聊天会话
removeChat(chatId);

// 设置加载状态
setLoading(true);

// 设置错误信息
setError('发生错误');
```

## 自动数据加载

系统会在页面刷新后自动调用 `api.getAll()` 获取数据并保存到store中。这个功能通过 `PageRefreshManager` 实现。

### 数据加载流程

1. 用户登录成功后，`PageRefreshManager` 被启用
2. 页面刷新时，触发 `load` 事件
3. 执行 `getLastLoginInfo` 操作
4. 获取用户信息后调用 `api.getAll(username)`
5. 将返回的数据保存到 `SystemStore` 中

## 在组件中使用

### 示例1: 显示代理列表

```typescript
import React from 'react';
import { List, Card, Tag } from 'antd';
import { useSystemStore } from '../stores/systemStore';
import type { Agent } from '../types/agent';

const AgentList = () => {
  const { agents } = useSystemStore();

  return (
    <List
      dataSource={agents}
      renderItem={(agent: Agent) => (
        <List.Item>
          <Card title={agent.card.name}>
            <p>{agent.card.description}</p>
            <Tag color="blue">{agent.card.version}</Tag>
          </Card>
        </List.Item>
      )}
    />
  );
};
```

### 示例2: 显示聊天会话列表

```typescript
import React from 'react';
import { List, Card, Badge, Avatar } from 'antd';
import { useSystemStore } from '../stores/systemStore';
import type { Chat } from '../pages/Chat/types/chat';

const ChatList = () => {
  const { chats } = useSystemStore();

  return (
    <List
      dataSource={chats}
      renderItem={(chat: Chat) => (
        <List.Item>
          <Card>
            <List.Item.Meta
              avatar={
                <Badge count={chat.unreadCount}>
                  <Avatar>{chat.name[0]}</Avatar>
                </Badge>
              }
              title={chat.name}
              description={chat.lastMessage}
            />
            <div>{chat.lastMessageTime}</div>
          </Card>
        </List.Item>
      )}
    />
  );
};
```

### 示例3: 显示统计数据

```typescript
import React from 'react';
import { Statistic, Row, Col } from 'antd';
import { useSystemStore } from '../stores/systemStore';

const Statistics = () => {
  const { agents, skills, tools, tasks, vehicles, chats } = useSystemStore();

  return (
    <Row gutter={16}>
      <Col span={4}>
        <Statistic title="代理" value={agents.length} />
      </Col>
      <Col span={4}>
        <Statistic title="技能" value={skills.length} />
      </Col>
      <Col span={4}>
        <Statistic title="工具" value={tools.length} />
      </Col>
      <Col span={4}>
        <Statistic title="任务" value={tasks.length} />
      </Col>
      <Col span={4}>
        <Statistic title="车辆" value={vehicles.length} />
      </Col>
      <Col span={4}>
        <Statistic title="聊天会话" value={chats.length} />
      </Col>
    </Row>
  );
};
```

### 示例4: 使用类型安全的组件

```typescript
import React from 'react';
import type { Agent, Skill, Task, Chat } from '../types';

interface DataDisplayProps {
  agents: Agent[];
  skills: Skill[];
  tasks: Task[];
  chats: Chat[];
}

const DataDisplay: React.FC<DataDisplayProps> = ({ agents, skills, tasks, chats }) => {
  return (
    <div>
      <h2>代理数量: {agents.length}</h2>
      <h2>技能数量: {skills.length}</h2>
      <h2>任务数量: {tasks.length}</h2>
      <h2>聊天会话数量: {chats.length}</h2>
    </div>
  );
};
```

## 状态管理

### 状态结构

```typescript
interface SystemState {
  // 数据状态
  token: string | null;
  agents: Agent[];
  skills: Skill[];
  tools: Tool[];
  tasks: Task[];
  vehicles: Vehicle[];
  settings: Settings | null;
  knowledges: Knowledge;
  chats: Chat[];
  
  // 加载状态
  isLoading: boolean;
  error: string | null;
  
  // 操作方法...
}
```

### 状态更新

- `setData()`: 设置完整数据
- `setLoading()`: 设置加载状态
- `setError()`: 设置错误信息
- `clearData()`: 清空所有数据

### Chat相关操作

- `setChats()`: 设置聊天会话列表
- `addChat()`: 添加新聊天会话
- `updateChat()`: 更新聊天会话
- `removeChat()`: 删除聊天会话

## 注意事项

1. **数据加载**: 数据会在页面刷新后自动加载，无需手动调用
2. **状态同步**: 所有组件都会自动同步到最新的数据状态
3. **错误处理**: 注意检查 `isLoading` 和 `error` 状态
4. **性能优化**: 大量数据时考虑使用虚拟滚动或分页
5. **类型安全**: 使用 `import type` 导入类型，避免运行时导入
6. **Chat类型**: 现在使用 `Chat` 类型，包含完整的聊天会话信息

## 扩展功能

### 添加新的数据类型

1. 在 `src/types/` 目录下创建新的类型文件
2. 定义相关的接口
3. 在 `src/types/index.ts` 中导出新类型
4. 在 `systemStore.ts` 中添加相应的状态和操作方法

### 添加新的操作方法

```typescript
// 在 SystemState 接口中添加
newMethod: (param: any) => void;

// 在 store 实现中添加
newMethod: (param) => set((state) => ({
  // 更新逻辑
})),
```

## 相关文件

- `systemStore.ts`: 主要store实现
- `index.ts`: store统一导出
- `../types/`: 所有类型定义文件
- `../types/index.ts`: 类型统一导出
- `../pages/Chat/types/chat.ts`: Chat相关类型定义
- `../services/events/PageRefreshManager.ts`: 自动数据加载
- `../components/DataDisplay.tsx`: 数据展示组件示例
- `../pages/Dashboard/Dashboard.tsx`: 使用示例
- `../types/README.md`: 类型管理说明 