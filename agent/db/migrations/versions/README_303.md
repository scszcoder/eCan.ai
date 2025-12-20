# Migration 3.0.2 to 3.0.3

## 概述

此迁移包含两个主要变更：
1. 修改 `agent_task_rels` 表，将 `vehicle_id` 字段从 `NOT NULL` 改为 `NULL`（可选）
2. 修改 `agents` 表，将 `title` 字段从 `String` 改为 `JSON`（数组）

## 变更内容

### 修改的表
- `agent_task_rels`
- `agents`

### 修改的字段

#### agent_task_rels 表
- `vehicle_id`: `VARCHAR(64) NOT NULL` → `VARCHAR(64) NULL`

#### agents 表
- `title`: `VARCHAR(128)` → `JSON`

## 业务逻辑

### 变更 1：vehicle_id 可选

#### 修改原因
1. **关联关系与执行分离**：agent-task 关联关系应该独立于任务执行环境
2. **灵活性**：允许先定义 agent 可以执行哪些 task，稍后再分配执行的 vehicle
3. **动态调度**：支持在任务调度时动态分配 vehicle

### 变更 2：title 改为 JSON 数组

#### 修改原因
1. **数据一致性**：与其他数组字段（`personality_traits`, `skills`, `tasks`）保持一致
2. **前端需求**：前端使用多选下拉框，需要数组格式
3. **简化逻辑**：统一处理所有数组字段，无需特殊逻辑
4. **扩展性**：支持一个 agent 拥有多个 title

### 使用场景

#### 场景 1：创建关联时不指定 vehicle
```python
# 定义 agent 可以执行的 tasks
agent_task_rel = DBAgentTaskRel(
    agent_id='agent_123',
    task_id='task_456',
    vehicle_id=None  # ✅ 可以为空
)
```

#### 场景 2：任务调度时分配 vehicle
```python
# 调度任务时分配 vehicle
agent_task_rel.vehicle_id = 'vehicle_8'
agent_task_rel.status = 'running'
```

## 迁移过程

### SQLite 限制
SQLite 不支持直接修改列约束，因此使用以下步骤：

1. 创建新表 `agent_task_rels_new`（vehicle_id 为 NULL）
2. 复制数据：`INSERT INTO agent_task_rels_new SELECT * FROM agent_task_rels`
3. 删除旧表：`DROP TABLE agent_task_rels`
4. 重命名新表：`ALTER TABLE agent_task_rels_new RENAME TO agent_task_rels`

### 数据安全
- ✅ 保留所有现有数据
- ✅ 保留所有索引和外键约束
- ✅ 事务保护，失败时回滚

## 执行迁移

### 自动执行
迁移会在应用启动时自动检测并执行：

```python
# 应用启动时
migration_manager = MigrationManager(engine)
migration_manager.migrate_to_latest()
```

### 手动执行
```bash
# 使用迁移 CLI
python -m agent.db.migrations.migration_cli upgrade

# 或者指定版本
python -m agent.db.migrations.migration_cli upgrade --target-version 3.0.3
```

## 验证

迁移完成后会自动验证：

1. ✅ `agent_task_rels` 表存在
2. ✅ `vehicle_id` 列存在
3. ✅ `vehicle_id` 列允许 NULL 值

## 回滚

### 注意事项
回滚到 3.0.2 需要满足条件：
- ⚠️ 所有 `agent_task_rels` 记录的 `vehicle_id` 必须非空
- ⚠️ 如果有 NULL 值，回滚会失败

### 回滚命令
```bash
python -m agent.db.migrations.migration_cli downgrade --target-version 3.0.2
```

## 影响范围

### 受影响的代码
- ✅ `agent/db/models/association_models.py` - 模型定义已更新
- ✅ `agent/db/services/db_agent_service.py` - 创建关联时 vehicle_id 可选

### 不受影响的功能
- ✅ 现有的 agent-task 关联数据
- ✅ 任务执行逻辑
- ✅ 其他表和关联

## 测试

### 测试场景
1. ✅ 创建 agent-task 关联，vehicle_id = None
2. ✅ 创建 agent-task 关联，vehicle_id = 'vehicle_8'
3. ✅ 更新现有关联的 vehicle_id
4. ✅ 查询包含 NULL vehicle_id 的关联

### 预期结果
所有场景都应该正常工作，不会出现 NOT NULL 约束错误。

## 版本信息

- **当前版本**: 3.0.3
- **上一版本**: 3.0.2
- **迁移文件**: `migration_302_to_303.py`
- **创建日期**: 2025-10-10
