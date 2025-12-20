# eCan.ai 数据库模块设计规范

## 目录结构设计

```
agent/db/
├── __init__.py                     # 统一导出接口
├── ecan_db_manager.py              # 统一数据库管理器
├── core/                           # 核心数据库组件
│   ├── __init__.py
│   ├── base.py                     # 数据库基础配置和连接
│   ├── models.py                   # 模型导入（向后兼容）
│   └── migration.py                # 数据库迁移工具
├── models/                         # 数据库模型层 
│   ├── __init__.py
│   ├── base_model.py               # 模型基类和混入类
│   ├── chat_model.py               # 聊天相关模型
│   ├── message_model.py            # 消息相关模型
│   ├── user_model.py               # 用户相关模型
│   └── version_model.py            # 版本管理模型
├── services/                       # 数据库服务层
│   ├── __init__.py
│   ├── db_chat_service.py             # 聊天服务
│   ├── base_service.py             # 服务基类
│   └── singleton.py                # 单例模式实现
├── utils/                          # 数据库工具
│   ├── __init__.py
│   └── content_schema.py           # 内容模式定义
└── tests/                          # 测试文件目录
    ├── __init__.py
    ├── test_chat_service.py
    ├── test_models.py
    └── test_migration.py
```

## 命名规范

### 文件命名
- 使用 snake_case 命名法
- 模型文件：`models.py`
- 服务文件：`*_service.py`
- 工具文件：`*_utils.py` 或具体功能名
- 测试文件：`test_*.py`

### 类命名
- 使用 PascalCase 命名法
- 模型类：直接使用实体名，如 `Chat`, `Message`
- 服务类：`*Service`，如 `ChatService`
- 工具类：`*Manager`, `*Helper`, `*Util`

### 模块组织原则
1. **分层架构**：core -> services -> repositories
2. **单一职责**：每个模块只负责一个特定功能
3. **依赖方向**：高层模块依赖低层模块
4. **可扩展性**：便于添加新的服务和模型

## 模块职责

### core/ - 核心数据库组件
- `base.py`: 数据库连接、引擎创建、会话管理
- `models.py`: 模型导入（向后兼容，已废弃）
- `migration.py`: 数据库版本管理和迁移工具

### models/ - 数据库模型层 ⭐ 新增
- `base_model.py`: 模型基类和混入类
  - `BaseModel`: 所有模型的基类，提供通用字段和方法
  - `TimestampMixin`: 时间戳混入类
  - `SoftDeleteMixin`: 软删除混入类
  - `ExtensibleMixin`: 可扩展字段混入类
- `chat_model.py`: 聊天相关模型
  - `Chat`: 聊天会话模型
  - `Member`: 聊天成员模型
  - `ChatNotification`: 聊天通知模型
- `message_model.py`: 消息相关模型
  - `Message`: 消息模型
  - `Attachment`: 附件模型
- `user_model.py`: 用户相关模型
  - `User`: 用户模型
  - `UserProfile`: 用户资料模型
  - `UserSession`: 用户会话模型
- `version_model.py`: 版本管理模型
  - `DBVersion`: 数据库版本模型
  - `MigrationLog`: 迁移日志模型

## 迁移计划

### 阶段1：重构现有文件
1. `models.py` → `core/models.py`
2. `migration.py` → `core/migration.py`
3. 创建 `core/base.py` 统一数据库配置

### 阶段2：迁移服务层
1. `db_chat_service.py` → `services/db_chat_service.py`
2. 提取 `SingletonMeta` → `services/singleton.py`
3. 创建 `services/base_service.py`

### 阶段3：迁移工具
1. `chat_utils.py` → `utils/content_schema.py`
2. 创建其他必要的工具模块

### 阶段4：迁移测试
1. 所有测试文件移动到 `tests/` 目录
2. 更新测试导入路径
