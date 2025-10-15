# Cloud API 离线同步模块

## 📁 目录结构

```
agent/cloud_api/
├── README.md                      # 本文件
├── cloud_api.py                   # 云端 API 基础函数
├── cloud_api_service.py           # 云端 API 同步服务
├── offline_sync_queue.py                  # 同步队列（离线缓存）⭐
├── offline_sync_manager.py                # 同步管理器（智能同步）⭐
│
├── mappings/                      # 字段映射配置文件
│   ├── skill_mapping.json         # Skill 字段映射
│   ├── task_mapping.json          # Task 字段映射
│   ├── agent_mapping.json         # Agent 字段映射
│   └── tool_mapping.json          # Tool 字段映射
│
└── docs/                          # 详细文档
    ├── OFFLINE_SYNC_GUIDE.md      # 离线同步详细指南
    └── ...
```

---

## 🎯 核心功能

### 1. 离线同步

**网络容错** - 网络不好时自动缓存，网络恢复后自动同步

```python
from agent.cloud_api.offline_sync_manager import get_sync_manager

manager = get_sync_manager()

# 同步数据（自动处理网络问题）
result = manager.sync_to_cloud('skill', skill_data, 'add')

if result['synced']:
    print("✅ 已同步到云端")
elif result['cached']:
    print("💾 已缓存，等待网络恢复")
```

### 2. 启动同步

**应用启动时** - 优先同步缓存数据，然后启动定时器

```python
# 在 MainWindow._sync_startup_sync() 中自动执行
def _sync_startup_sync(self):
    # Step 1: 同步缓存到云端（阻塞）
    manager = get_sync_manager()
    queue = get_sync_queue()
    
    if queue.get_stats()['pending_count'] > 0:
        manager.sync_pending_queue()
    
    # Step 2: 启动定时器（每5分钟）
    manager.start_auto_retry(interval=300)
```

### 3. 登出清理

**应用登出时** - 停止定时器，释放资源

```python
# 在 MainWindow._async_cleanup_and_logout() 中自动执行
async def _async_cleanup_and_logout(self):
    manager = get_sync_manager()
    manager.stop_auto_retry()
```

---

## 🏗️ 架构设计

### 整体架构

```
应用层 (skill_handler, task_handler, etc.)
    ↓
OfflineSyncManager (智能同步管理器)
    ↓
┌─────────┴─────────┐
│                   │
CloudAPIService   OfflineSyncQueue
(云端同步)         (本地队列)
│                   │
AWS Lambda      {appdata}/offline_sync_queue/
                ├── pending_sync.json
                └── failed_sync.json
```

### 核心组件

#### OfflineSyncQueue - 同步队列

**文件**: `offline_sync_queue.py`

**功能**:
- 管理待同步任务队列
- 持久化到本地文件
- 支持重试和失败处理
- 线程安全

**缓存位置**:
- **macOS**: `~/Library/Application Support/eCan.ai/offline_sync_queue/`
- **Windows**: `%LOCALAPPDATA%\eCan.ai\sync_queue\`
- **Linux**: `~/.local/share/eCan.ai/offline_sync_queue/`
- **开发模式**: `{项目根目录}/offline_sync_queue/`

#### OfflineSyncManager - 同步管理器

**文件**: `offline_sync_manager.py`

**功能**:
- 智能同步（在线/离线自动切换）
- 同步队列中的任务
- 启动/停止自动重试定时器

**关键方法**:
```python
# 同步数据到云端
sync_to_cloud(data_type, data, operation) -> Dict

# 同步队列中的任务
sync_pending_queue() -> Dict

# 启动自动重试定时器
start_auto_retry(interval=300)

# 停止自动重试定时器
stop_auto_retry()

# 获取队列统计
get_stats() -> Dict
```

---

## 🔄 完整生命周期

### 1. 应用启动

```
用户登录
  ↓
MainWindow 初始化
  ↓
_sync_startup_sync() [阻塞执行]
  ↓
检查队列：有待同步数据？
  ├─ 是：阻塞式同步所有缓存
  └─ 否：跳过
  ↓
启动定时器（每5分钟自动重试）
  ↓
继续初始化
```

### 2. 运行时同步

```
用户保存 Skill
  ↓
skill_handler.handle_save_agent_skill()
  ↓
1. 保存到本地数据库
  ↓
2. _trigger_cloud_sync(skill_data, 'update')
  ↓
OfflineSyncManager.sync_to_cloud()
  ↓
┌─────────────┴─────────────┐
│                           │
网络好                    网络不好
│                           │
CloudAPIService           OfflineSyncQueue
│                           │
AWS Lambda                缓存到文件
│                           │
✅ 成功                    💾 缓存
                            │
                            ↓
                        定时器自动重试
```

### 3. 应用登出

```
用户登出
  ↓
_async_cleanup_and_logout()
  ↓
停止定时器
  ↓
清理资源
  ↓
应用关闭
```

---

## 💻 使用示例

### 在 Handler 中集成

```python
# skill_handler.py

def _trigger_cloud_sync(skill_data: Dict[str, Any], operation: str = 'add') -> None:
    """同步到云端（自动处理离线）"""
    try:
        from agent.cloud_api.offline_sync_manager import get_sync_manager
        
        manager = get_sync_manager()
        result = manager.sync_to_cloud('skill', skill_data, operation)
        
        if result['synced']:
            logger.info(f"✅ Skill synced to cloud: {operation}")
        elif result['cached']:
            logger.info(f"💾 Skill cached for later sync: {operation}")
            
    except Exception as e:
        logger.error(f"Failed to sync skill to cloud: {e}")


@IPCHandlerRegistry.handler('save_agent_skill')
def handle_save_agent_skill(request, params):
    # 1. 保存到本地数据库
    skill_service.update_skill(skill_id, skill_data)
    
    # 2. 同步到云端
    _trigger_cloud_sync(skill_data, 'update')
    
    return create_success_response(data={'skill_id': skill_id})
```

### 监控队列状态

```python
from agent.cloud_api.offline_sync_manager import get_sync_manager

manager = get_sync_manager()
stats = manager.get_stats()

print(f"待同步: {stats['pending_count']}")
print(f"失败: {stats['failed_count']}")
print(f"按类型: {stats['pending_by_type']}")
```

---

## 📊 数据流

### 队列数据格式

```json
{
  "id": "skill_add_1697123456789",
  "data_type": "skill",
  "operation": "add",
  "data": {
    "id": "123",
    "name": "Test Skill",
    "diagram": {...}
  },
  "created_at": "2025-10-11T20:00:00",
  "retry_count": 0,
  "status": "pending"
}
```

### 同步结果格式

```python
{
    'success': True,      # 是否成功（同步或缓存）
    'synced': True,       # 是否已同步到云端
    'cached': False,      # 是否已缓存到本地
    'task_id': None,      # 缓存任务ID（如果缓存）
    'message': '...'      # 结果消息
}
```

---

## 🔧 配置参数

### 队列配置

```python
# 最大重试次数
MAX_RETRIES = 3

# 缓存目录（自动使用 app_info.appdata_path）
# macOS: ~/Library/Application Support/eCan.ai/offline_sync_queue/
# Windows: %LOCALAPPDATA%\eCan.ai\sync_queue\
# Linux: ~/.local/share/eCan.ai/offline_sync_queue/
```

### 定时器配置

```python
# 自动重试间隔（秒）
AUTO_RETRY_INTERVAL = 300  # 5 分钟

# 启动定时器
manager.start_auto_retry(interval=300)

# 停止定时器
manager.stop_auto_retry()
```

---

## 📝 日志输出

### 启动同步

```
[MainWindow] 🚀 Starting startup sync (blocking)...
[MainWindow] 📤 Found 5 pending tasks, syncing to cloud first...
[MainWindow] Pending by type: {'skill': 3, 'task': 2}
[MainWindow] ✅ Pending queue sync completed:
  - Total: 5
  - Synced: 4
  - Failed: 1
[MainWindow] 🔄 Starting auto retry timer for periodic cache sync...
[MainWindow] ✅ Auto retry timer started (interval: 300s)
```

### 运行时同步

```
[skill_handler] ✅ Skill synced to cloud: update - Test Skill
[skill_handler] 💾 Skill cached for later sync: add - New Skill
```

### 登出清理

```
[MainWindow] 🧹 Starting comprehensive cleanup for logout...
[MainWindow] ✅ Sync manager auto retry timer stopped
```

---

## 🎯 核心优势

1. **用户无感** - 自动处理网络问题，用户无需关心
2. **数据可靠** - 确保数据不丢失，自动缓存和重试
3. **易于集成** - 简单的 API，几行代码即可
4. **跨平台** - 自动适配不同操作系统的缓存目录
5. **自动化** - 启动时自动同步，后台自动重试，登出时自动清理

---

## 🔍 故障排查

### 查看队列状态

```python
from agent.cloud_api.offline_sync_queue import get_sync_queue

queue = get_sync_queue()
stats = queue.get_stats()

print(f"待同步: {stats['pending_count']}")
print(f"失败: {stats['failed_count']}")

# 查看待同步任务
pending = queue.get_pending_tasks()
for task in pending:
    print(f"Task: {task['id']}, Type: {task['data_type']}, Retry: {task['retry_count']}")
```

### 手动同步队列

```python
from agent.cloud_api.offline_sync_manager import get_sync_manager

manager = get_sync_manager()
result = manager.sync_pending_queue()

print(f"Total: {result['total']}")
print(f"Synced: {result['synced']}")
print(f"Failed: {result['failed']}")
```

### 清理队列

```python
queue = get_sync_queue()

# 清空待同步队列
queue.clear_pending()

# 清空失败队列
queue.clear_failed()
```

---

## 📖 详细文档

- **[docs/OFFLINE_SYNC_GUIDE.md](docs/OFFLINE_SYNC_GUIDE.md)** - 离线同步详细指南

---

## 🎉 总结

离线同步功能提供了完整的网络容错能力：

- ✅ **启动时** - 优先同步缓存数据
- ✅ **运行时** - 自动处理网络问题
- ✅ **后台** - 定时器自动重试
- ✅ **登出时** - 优雅关闭定时器

**一行代码即可使用，完全自动化！** 🚀
