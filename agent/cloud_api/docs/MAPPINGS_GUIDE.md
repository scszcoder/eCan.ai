# Mapping 配置说明

## ⚠️ 重要概念区分

### DataType 的实际含义

代码中的 `DataType` 枚举值与实际用途的对应关系：

| DataType 枚举 | 实际用途 | Mapping 文件 | GraphQL 类型 |
|--------------|---------|-------------|-------------|
| `AGENT` | Agent 实体 | agent_mapping.json | `input Agent` |
| `SKILL` | **Agent-Skill 关系** | skill_mapping.json | `input AgentSkillRelation` |
| `TASK` | **Agent-Task 关系** | task_mapping.json | `input AgentTaskRelation` |
| `TOOL` | **Agent-Tool 关系** | tool_mapping.json | `input AgentToolRelation` |

**注意**: 
- ❌ `DataType.SKILL` **不是** Skill 实体
- ✅ `DataType.SKILL` **是** Agent-Skill 关系

---

## 📋 Mapping 文件内容

### 1. agent_mapping.json
**用途**: Agent 实体字段映射

**包含字段**:
- 实体字段: `name`, `description`, `gender`, `birthday`, `org_id`, etc.
- JSON 字段: `personalities`, `extra_data`, `capabilities`

---

### 2. skill_mapping.json
**用途**: Agent-Skill 关系字段映射

**包含字段**:
- ✅ 关系字段: `agid`, `skid`, `owner`, `status`, `langgraph`, `proficiency`
- ❌ **不包含** Skill 实体字段: `name`, `description`, `flowgram`, `path`, `price`

**为什么?**
- 这是**关联表**，只存储关系元数据
- Skill 的名称、描述等属于 Skill 实体，不在关联表中

---

### 3. task_mapping.json
**用途**: Agent-Task 关系字段映射

**包含字段**:
- ✅ 关系字段: `agid`, `task_id`, `owner`, `status`, `vehicle_id`, `assigned_at`
- ❌ **不包含** Task 实体字段: `name`, `description`, `objectives`, `schedule`, `metadata`, `priority`

**为什么?**
- 这是**关联表**，只存储关系元数据
- Task 的名称、目标等属于 Task 实体，不在关联表中

---

### 4. tool_mapping.json
**用途**: Agent-Tool 关系字段映射

**包含字段**:
- ✅ 关系字段: `agid`, `tool_id`, `owner`, `permission`, `granted_at`
- ❌ **不包含** Tool 实体字段: `name`, `description`, `protocol`, `metadata`, `link`, `status`, `price`

**为什么?**
- 这是**关联表**，只存储关系元数据
- Tool 的名称、协议等属于 Tool 实体，不在关联表中

---

## 🔍 常见错误

### 错误 1: 在关联表中包含实体字段

❌ **错误示例** (task_mapping.json):
```json
{
  "cloud_required_fields": {
    "agid": "",
    "task_id": "",
    "name": "",           // ❌ 错误！name 是 Task 实体字段
    "description": "",    // ❌ 错误！description 是 Task 实体字段
    "objectives": []      // ❌ 错误！objectives 是 Task 实体字段
  }
}
```

✅ **正确示例** (task_mapping.json):
```json
{
  "cloud_required_fields": {
    "agid": "",           // ✅ 关系字段
    "task_id": "",        // ✅ 关系字段
    "owner": "",          // ✅ 关系字段
    "status": "assigned"  // ✅ 关系字段
  }
}
```

### 错误 2: GraphQL 验证错误

当 mapping 包含错误字段时，会收到以下错误：

```
Validation error of type WrongType: 
argument 'input[0]' contains a field not in 'AgentTaskRelation': 'name'
```

**原因**: 
- Mapping 中定义了 `name` 字段
- 但 `input AgentTaskRelation` 中没有 `name` 字段
- GraphQL 验证失败

---

## 📊 数据流程

### Agent-Task 关联流程

1. **本地数据**:
   ```python
   {
     "agid": "agent_123",
     "task_id": "task_456",
     "owner": "user@example.com",
     "status": "assigned"
   }
   ```

2. **Schema 转换** (使用 task_mapping.json):
   ```python
   # cloud_required_fields 确保必需字段存在
   {
     "agid": "agent_123",
     "task_id": "task_456",
     "owner": "user@example.com",
     "status": "assigned"
   }
   ```

3. **GraphQL Mutation**:
   ```graphql
   mutation {
     addAgentTaskRelations(input: [{
       agid: "agent_123"
       task_id: "task_456"
       owner: "user@example.com"
       status: "assigned"
     }])
   }
   ```

4. **AppSync 验证**:
   - ✅ 检查所有字段是否在 `input AgentTaskRelation` 中定义
   - ✅ 验证通过，执行 Mutation

---

## ✅ 最佳实践

1. **明确区分实体和关系**
   - 实体: Agent, Skill, Task, Tool
   - 关系: AgentSkillRelation, AgentTaskRelation, AgentToolRelation

2. **Mapping 只包含对应类型的字段**
   - Agent mapping → Agent 实体字段
   - Skill mapping → AgentSkillRelation 关系字段

3. **使用正确的 GraphQL 类型**
   - 实体: `input Agent`, `input AgentSkill`, `input AgentTask`, `input AgentTool`
   - 关系: `input AgentSkillRelation`, `input AgentTaskRelation`, `input AgentToolRelation`

4. **定期验证 Mapping**
   - 确保 mapping 字段与 Schema 定义一致
   - 检查是否有多余的字段

---

**最后更新**: 2025-10-14
