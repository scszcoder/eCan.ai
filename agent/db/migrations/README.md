# 数据库迁移系统

## 🏗️ 架构概述

这是一个现代化的数据库迁移系统，支持版本化管理、自动发现和链式执行。

### 核心特性

- **版本化管理**：每个版本对应独立的迁移脚本
- **自动发现**：系统自动扫描和加载迁移脚本
- **链式执行**：支持跨版本的连续迁移
- **回滚支持**：每个迁移都可以回滚（可选）
- **扩展友好**：添加新版本只需创建新的迁移文件

## 📁 目录结构

```
agent/db/migrations/
├── __init__.py                    # 包导出
├── base_migration.py              # 迁移基类
├── migration_manager.py           # 迁移管理器
├── migration_cli.py               # 命令行工具
├── README.md                      # 使用指南
└── versions/                      # 迁移脚本目录
    ├── __init__.py
    ├── migration_001_to_101.py    # 1.0.0 → 1.0.1
    ├── migration_101_to_200.py    # 1.0.1 → 2.0.0
    └── migration_200_to_300.py    # 2.0.0 → 3.0.0
```

## 🚀 快速开始

### 1. 检查迁移状态

```bash
python3 agent/db/migrations/migration_cli.py status
```

### 2. 运行迁移到最新版本

```bash
python3 agent/db/migrations/migration_cli.py migrate
```

### 3. 查看可用的迁移

```bash
python3 agent/db/migrations/migration_cli.py list
```

## 📝 创建新的迁移

### 使用命令行工具创建

```bash
python3 agent/db/migrations/migration_cli.py create 3.0.0 3.1.0 "Add user preferences table"
```

这将创建一个新的迁移模板文件：`migration_300_to_310.py`

### 手动创建迁移文件

1. 在 `versions/` 目录下创建新文件：`migration_XXX_to_YYY.py`
2. 继承 `BaseMigration` 类
3. 实现必要的方法

## 🔧 迁移脚本示例

```python
"""
Migration from version 3.0.0 to 3.1.0

Add user preferences table for storing user-specific settings.
"""

from sqlalchemy.orm import Session
from ..base_migration import BaseMigration
from utils.logger_helper import logger_helper as logger


class Migration300To310(BaseMigration):
    """Migration from 3.0.0 to 3.1.0"""
    
    @property
    def version(self) -> str:
        return "3.1.0"
    
    @property
    def previous_version(self) -> str:
        return "3.0.0"
    
    @property
    def description(self) -> str:
        return "Add user preferences table"
    
    def upgrade(self, session: Session) -> bool:
        """执行数据库升级"""
        try:
            if not self.table_exists('user_preferences'):
                sql = """
                CREATE TABLE user_preferences (
                    id VARCHAR(64) PRIMARY KEY,
                    user_id VARCHAR(64) NOT NULL,
                    preference_key VARCHAR(100) NOT NULL,
                    preference_value JSON,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    UNIQUE(user_id, preference_key)
                )
                """
                if not self.execute_sql(session, sql):
                    return False
                
                logger.info("Created user_preferences table")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to upgrade to 3.1.0: {e}")
            return False
    
    def validate_postconditions(self, session: Session) -> bool:
        """验证迁移是否成功"""
        return self.table_exists('user_preferences')
    
    def downgrade(self, session: Session) -> bool:
        """执行数据库降级（可选）"""
        try:
            if self.table_exists('user_preferences'):
                sql = "DROP TABLE user_preferences"
                if not self.execute_sql(session, sql):
                    return False
                logger.info("Dropped user_preferences table")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to downgrade from 3.1.0: {e}")
            return False
```

## 🛠️ 在代码中使用

### 基本使用

```python
from agent.db.core import get_engine
from agent.db.migrations import MigrationManager

# 创建迁移管理器
engine = get_engine('your_database.db')
manager = MigrationManager(engine)

# 检查当前版本
current_version = manager.get_current_version()
print(f"Current version: {current_version}")

# 迁移到最新版本
success = manager.migrate_to_latest()
if success:
    print("Migration completed successfully")
else:
    print("Migration failed")

# 迁移到特定版本
success = manager.migrate_to_version('3.1.0')
```

### 在 ECDBMgr 中集成

```python
class ECDBMgr:
    def _run_migrations(self) -> bool:
        try:
            # 使用新的迁移管理器
            migrator = MigrationManager(self.engine)
            success = migrator.migrate_to_latest()
            
            if success:
                logger.info("Database migrations completed successfully")
            else:
                logger.warning("Database migrations failed")
            
            return success
            
        except Exception as e:
            logger.error(f"Database migration failed: {e}")
            return False
```

## 📋 最佳实践

### 1. 命名规范

- 文件名：`migration_XXX_to_YYY.py`
- 类名：`MigrationXXXToYYY`
- 版本号：使用语义化版本（如 `3.1.0`）

### 2. 迁移设计原则

- **原子性**：每个迁移应该是原子操作
- **幂等性**：多次执行同一迁移应该安全
- **向前兼容**：新版本应该兼容旧数据
- **测试充分**：在生产环境前充分测试

### 3. 错误处理

- 使用 `try-except` 包装所有数据库操作
- 提供详细的错误日志
- 在失败时进行适当的清理

### 4. 验证机制

- 实现 `validate_postconditions()` 方法
- 检查表、列、索引是否正确创建
- 验证数据完整性

## 🔄 迁移流程

1. **发现阶段**：扫描 `versions/` 目录，加载所有迁移类
2. **规划阶段**：根据当前版本和目标版本，计算迁移路径
3. **执行阶段**：按顺序执行每个迁移的 `upgrade()` 方法
4. **验证阶段**：执行 `validate_postconditions()` 验证
5. **更新阶段**：更新数据库版本记录

## 🚨 注意事项

### SQLite 限制

- SQLite 不支持 `DROP COLUMN`，降级功能有限
- 某些 `ALTER TABLE` 操作需要特殊处理
- 建议在 PostgreSQL/MySQL 中进行复杂的模式变更

### 生产环境

- **备份数据库**：迁移前务必备份
- **测试环境验证**：先在测试环境验证迁移
- **监控日志**：密切关注迁移过程的日志
- **回滚计划**：准备回滚方案

## 🎯 未来扩展

### 计划中的功能

- **并行迁移**：支持并行执行独立的迁移
- **条件迁移**：根据数据库状态决定是否执行
- **数据迁移**：支持数据转换和清理
- **性能监控**：迁移执行时间和性能统计
- **Web 界面**：图形化的迁移管理界面

### 添加新版本的步骤

1. 使用 CLI 工具创建迁移模板
2. 实现迁移逻辑
3. 测试迁移和回滚
4. 提交代码
5. 在生产环境执行迁移

## 📞 支持

如果遇到问题或需要帮助，请：

1. 查看日志文件了解详细错误信息
2. 检查迁移脚本的实现
3. 验证数据库连接和权限
4. 联系开发团队获取支持

---

**记住**：数据库迁移是一个关键操作，请务必在生产环境中谨慎执行！
