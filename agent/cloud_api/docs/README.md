# Cloud API Offline Sync Module

## 📁 Directory Structure

```
agent/cloud_api/
├── README.md                      # This file
├── cloud_api.py                   # Cloud API base functions
├── cloud_api_service.py           # Cloud API sync service
├── offline_sync_queue.py                  # Sync queue (offline cache) ⭐
├── offline_sync_manager.py                # Sync manager (intelligent sync) ⭐
├── appsync_schema.graphql         # AWS AppSync GraphQL schema (reference only)
│
├── mappings/                      # Field mapping configuration files
│   ├── skill_mapping.json         # Skill field mapping
│   ├── task_mapping.json          # Task field mapping
│   ├── agent_mapping.json         # Agent field mapping
│   └── tool_mapping.json          # Tool field mapping
│
└── docs/                          # Detailed documentation
    ├── OFFLINE_SYNC_GUIDE.md      # Offline sync detailed guide
    ├── OFFLINE_SYNC_CONTROLS_SIMPLE.md   # Offline sync control switches (简化版) ⭐
    └── SCHEMA_SYNC_POLICY.md      # Schema sync policy ⭐
```

## ⚠️ Schema Sync Policy

**IMPORTANT**: When cloud schema changes are needed:

1. **Modify cloud schema first** (AWS AppSync)
2. **Update local mapping files** (`mappings/*.json`)
3. **DO NOT** add complex compatibility code for old schemas
4. **Keep code simple** - cloud is the source of truth

See [docs/SCHEMA_SYNC_POLICY.md](docs/SCHEMA_SYNC_POLICY.md) for details.

---

## 🎯 Core Features

### 1. Offline Sync

**Network Fault Tolerance** - Auto-cache when network is poor, auto-sync when network recovers

```python
from agent.cloud_api.offline_sync_manager import get_sync_manager

manager = get_sync_manager()

# Sync data (auto-handle network issues)
result = manager.sync_to_cloud('skill', skill_data, 'add')

if result['synced']:
    print("✅ Synced to cloud")
elif result['cached']:
    print("💾 Cached, waiting for network recovery")
```

### 2. Startup Sync

**On Application Startup** - Prioritize syncing cached data, then start timer

```python
# Auto-executed in MainWindow._sync_startup_sync()
def _sync_startup_sync(self):
    # Step 1: Sync cache to cloud (blocking)
    manager = get_sync_manager()
    queue = get_sync_queue()
    
    if queue.get_stats()['pending_count'] > 0:
        manager.sync_pending_queue()
    
    # Step 2: Start timer (every 5 minutes)
    manager.start_auto_retry(interval=300)
```

### 3. Logout Cleanup

**On Application Logout** - Stop timer, release resources

```python
# Auto-executed in MainWindow._async_cleanup_and_logout()
async def _async_cleanup_and_logout(self):
    manager = get_sync_manager()
    manager.stop_auto_retry()
```

### 4. Offline Sync Control Switch ⭐ NEW

**Control Offline Sync Behavior** - Simple class variable in OfflineSyncManager

直接修改 `/agent/cloud_api/offline_sync_manager.py` 中的类变量：

```python
class OfflineSyncManager:
    # Configuration variable for offline sync control
    OFFLINE_SYNC_ENABLED = True  # 启用/禁用离线同步功能
```

**使用场景**：
- **生产环境**：`OFFLINE_SYNC_ENABLED = True` - 启用离线同步，失败请求自动缓存
- **开发调试**：`OFFLINE_SYNC_ENABLED = False` - 禁用离线同步，看到真实错误，避免队列污染
- **测试**：`OFFLINE_SYNC_ENABLED = False` - 测试错误处理逻辑

---

## 🏗️ Architecture Design

### Overall Architecture

```
Application Layer (skill_handler, task_handler, etc.)
    ↓
OfflineSyncManager (Intelligent sync manager)
    ↓
┌─────────┴─────────┐
│                   │
CloudAPIService   OfflineSyncQueue
(Cloud sync)      (Local queue)
│                   │
AWS Lambda      {appdata}/offline_sync_queue/
                ├── pending_sync.json
                └── failed_sync.json
```

### Core Components

#### OfflineSyncQueue - Sync Queue

**File**: `offline_sync_queue.py`

**Features**:
- Manage pending sync task queue
- Persist to local files
- Support retry and failure handling
- Thread-safe

**Cache Location**:
- **macOS**: `~/Library/Application Support/eCan.ai/offline_sync_queue/`
- **Windows**: `%LOCALAPPDATA%\eCan.ai\sync_queue\`
- **Linux**: `~/.local/share/eCan.ai/offline_sync_queue/`
- **Development Mode**: `{project_root}/offline_sync_queue/`

#### OfflineSyncManager - Sync Manager

**File**: `offline_sync_manager.py`

**Features**:
- Intelligent sync (online/offline auto-switch)
- Sync tasks in queue
- Start/stop auto-retry timer

**Key Methods**:
```python
# Sync data to cloud
sync_to_cloud(data_type, data, operation) -> Dict

# Sync tasks in queue
sync_pending_queue() -> Dict

# Start auto-retry timer
start_auto_retry(interval=300)

# Stop auto-retry timer
stop_auto_retry()

# Get queue statistics
get_stats() -> Dict
```

---

## 🔄 Complete Lifecycle

### 1. Application Startup

```
User Login
  ↓
MainWindow Initialization
  ↓
_sync_startup_sync() [Blocking execution]
  ↓
Check queue: Pending sync data?
  ├─ Yes: Blocking sync all cache
  └─ No: Skip
  ↓
Start timer (auto-retry every 5 minutes)
  ↓
Continue initialization
```

### 2. Runtime Sync

```
User saves Skill
  ↓
skill_handler.handle_save_agent_skill()
  ↓
1. Save to local database
  ↓
2. _trigger_cloud_sync(skill_data, 'update')
  ↓
OfflineSyncManager.sync_to_cloud()
  ↓
┌─────────────┴─────────────┐
│                           │
Good Network              Poor Network
│                           │
CloudAPIService           OfflineSyncQueue
│                           │
AWS Lambda                Cache to file
│                           │
✅ Success                 💾 Cached
                            │
                            ↓
                        Timer auto-retry
```

### 3. Application Logout

```
User Logout
  ↓
_async_cleanup_and_logout()
  ↓
Stop timer
  ↓
Cleanup resources
  ↓
Application close
```

---

## 💻 Usage Examples

### Integration in Handler

```python
# skill_handler.py

def _trigger_cloud_sync(skill_data: Dict[str, Any], operation: str = 'add') -> None:
    """Sync to cloud (auto-handle offline)"""
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
    # 1. Save to local database
    skill_service.update_skill(skill_id, skill_data)
    
    # 2. Sync to cloud
    _trigger_cloud_sync(skill_data, 'update')
    
    return create_success_response(data={'skill_id': skill_id})
```

### Monitor Queue Status

```python
from agent.cloud_api.offline_sync_manager import get_sync_manager

manager = get_sync_manager()
stats = manager.get_stats()

print(f"Pending: {stats['pending_count']}")
print(f"Failed: {stats['failed_count']}")
print(f"By type: {stats['pending_by_type']}")
```

---

## 📊 Data Flow

### Queue Data Format

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

### Sync Result Format

```python
{
    'success': True,      # Whether successful (synced or cached)
    'synced': True,       # Whether synced to cloud
    'cached': False,      # Whether cached locally
    'task_id': None,      # Cache task ID (if cached)
    'message': '...'      # Result message
}
```

---

## 🔧 Configuration Parameters

### Queue Configuration

```python
# Max retry count
MAX_RETRIES = 3

# Cache directory (auto-use app_info.appdata_path)
# macOS: ~/Library/Application Support/eCan.ai/offline_sync_queue/
# Windows: %LOCALAPPDATA%\eCan.ai\offline_sync_queue/
# Linux: ~/.local/share/eCan.ai/offline_sync_queue/
```

### Timer Configuration

```python
# Auto-retry interval (seconds)
AUTO_RETRY_INTERVAL = 300  # 5 minutes

# Start timer
manager.start_auto_retry(interval=300)

# Stop timer
manager.stop_auto_retry()
```

---

## 📝 Log Output

### Startup Sync

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

### Runtime Sync

```
[skill_handler] ✅ Skill synced to cloud: update - Test Skill
[skill_handler] 💾 Skill cached for later sync: add - New Skill
```

### Logout Cleanup

```
[MainWindow] 🧹 Starting comprehensive cleanup for logout...
[MainWindow] ✅ Sync manager auto retry timer stopped
```

---

## 🎯 Core Advantages

1. **User Transparent** - Auto-handle network issues, users don't need to care
2. **Data Reliable** - Ensure no data loss, auto-cache and retry
3. **Easy Integration** - Simple API, just a few lines of code
4. **Cross-Platform** - Auto-adapt cache directories for different OS
5. **Automated** - Auto-sync on startup, auto-retry in background, auto-cleanup on logout

---

## 🔍 Troubleshooting

### Check Queue Status

```python
from agent.cloud_api.offline_sync_queue import get_sync_queue

queue = get_sync_queue()
stats = queue.get_stats()

print(f"Pending: {stats['pending_count']}")
print(f"Failed: {stats['failed_count']}")

# View pending tasks
pending = queue.get_pending_tasks()
for task in pending:
    print(f"Task: {task['id']}, Type: {task['data_type']}, Retry: {task['retry_count']}")
```

### Manual Queue Sync

```python
from agent.cloud_api.offline_sync_manager import get_sync_manager

manager = get_sync_manager()
result = manager.sync_pending_queue()

print(f"Total: {result['total']}")
print(f"Synced: {result['synced']}")
print(f"Failed: {result['failed']}")
```

### Clear Queue

```python
queue = get_sync_queue()

# Clear pending queue
queue.clear_pending()

# Clear failed queue
queue.clear_failed()
```

---

## 📖 Detailed Documentation

- **[docs/OFFLINE_SYNC_GUIDE.md](docs/OFFLINE_SYNC_GUIDE.md)** - Offline sync detailed guide

---

## 🎉 Summary

Offline sync feature provides complete network fault tolerance:

- ✅ **On Startup** - Prioritize syncing cached data
- ✅ **Runtime** - Auto-handle network issues
- ✅ **Background** - Timer auto-retry
- ✅ **On Logout** - Gracefully stop timer

**One line of code to use, fully automated!** 🚀
