# 代理管理机制完整文档

本文档总结了 eCan.ai 应用中完整的代理管理系统的设计、实现和使用方法。

## 📐 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    ProxyManager (核心)                          │
│                  agent/ec_skills/system_proxy.py                │
├─────────────────────────────────────────────────────────────────┤
│ • 每30秒自动检测系统代理状态                                     │
│ • 自动更新环境变量 (HTTP_PROXY, HTTPS_PROXY等)                  │
│ • 代理不可用时自动 del 环境变量                                  │
│ • 支持回调机制，通知所有注册的监听者                             │
└─────────────────────────┬───────────────────────────────────────┘
                          │ 触发回调
                          │
          ┌───────────────┴────────────────┐
          │                                │
          ▼                                ▼
┌──────────────────────┐        ┌──────────────────────┐
│    MainWindow        │        │  LightragServer      │
│  gui/MainGUI.py      │        │ knowledge/           │
│                      │        │ lightrag_server.py   │
├──────────────────────┤        ├──────────────────────┤
│ 初始化:              │        │ 初始化:              │
│ - 创建 self.llm      │        │ - 启动子进程         │
│ - 注册回调           │        │ - 后台注册回调       │
│                      │        │   (延迟0.5秒)        │
├──────────────────────┤        ├──────────────────────┤
│ 代理变化时:          │        │ 代理变化时:          │
│ - 重新创建 LLM       │        │ - 忽略初始2秒        │
│ - 更新所有 agents    │        │ - 停止子进程         │
│   的 skill_llm       │        │ - 等待端口释放       │
│ - 详细日志记录       │        │ - 重启子进程         │
│                      │        │ - 后台线程执行       │
├──────────────────────┤        ├──────────────────────┤
│ 清理:                │        │ 清理:                │
│ - logout() 时        │        │ - stop() 时          │
│   unregister 回调    │        │   unregister 回调    │
└──────────────────────┘        └──────────────────────┘
```

## 🔧 核心实现: ProxyManager

**位置**: `agent/ec_skills/system_proxy.py`

### 关键功能
1. 自动检测系统代理 (跨平台: Windows/macOS/Linux)
2. 测试代理连接性 (1秒超时)
3. 更新/清除环境变量
4. 回调机制

### 回调注册方法
```python
proxy_manager.register_callback(callback_func)
# 返回: unregister_func (用于清理)
```

### 回调函数签名
```python
def callback(proxies: Optional[Dict[str, str]]):
    """
    Args:
        proxies: None if proxy disabled/unavailable
                 Dict if proxy enabled (e.g. {'http://': '...', 'https://': '...'})
    """
```

### 环境变量管理
- **代理可用时**: `os.environ['HTTP_PROXY'] = '...'`
- **代理不可用时**: `del os.environ['HTTP_PROXY']`  # 正确方式
- **影响范围**: 父进程和所有后续创建的子进程

## 🎯 实现 1: MainWindow 的代理回调

**位置**: `gui/MainGUI.py`  
**方法名**: `_register_proxy_change_callback()`

### 实现逻辑
1. 获取 ProxyManager 实例
2. 定义回调函数 `on_proxy_change(proxies)`
3. 回调中:
   - 记录代理状态变化日志
   - 调用 `pick_llm()` 重新创建 LLM
   - 更新 `self.llm`
   - 遍历所有 agents，调用 `set_skill_llm()` 更新
4. 注册回调，保存 unregister 函数到 `self._proxy_callback_unregister`
5. `logout()` 时调用 unregister

### 关键代码
```python
def _register_proxy_change_callback(self):
    """Register callback with ProxyManager to recreate LLM instances."""
    proxy_manager = get_proxy_manager()
    if not proxy_manager:
        return
    
    def on_proxy_change(proxies):
        if proxies:
            logger.info(f"[MainWindow] 🌐 Proxy enabled - {proxy_info}")
        else:
            logger.info("[MainWindow] 🌐 Proxy disabled - using direct connection")
        
        # Recreate LLM
        new_llm = pick_llm(
            self.config_manager.general_settings.default_llm,
            self.config_manager.llm_manager.get_all_providers(),
            self.config_manager
        )
        
        if new_llm:
            self.llm = new_llm
            logger.info(f"[MainWindow] ✅ LLM recreated successfully")
            
            # Update all agents' skill_llm
            for agent in self.agents:
                if hasattr(agent, 'set_skill_llm'):
                    agent.set_skill_llm(self.llm)
    
    self._proxy_callback_unregister = proxy_manager.register_callback(on_proxy_change)
    logger.info("[MainWindow] ✅ Registered proxy change callback")

async def _async_cleanup_and_logout(self):
    """Cleanup during logout"""
    # Unregister proxy change callback
    if hasattr(self, '_proxy_callback_unregister') and self._proxy_callback_unregister:
        self._proxy_callback_unregister()
        self._proxy_callback_unregister = None
        logger.info("[MainWindow] ✅ Proxy change callback unregistered")
```

### 为什么需要重新创建 LLM
- LLM 内部的 httpx/openai client 在初始化时会读取并缓存代理配置
- 即使后续改变环境变量，已创建的 client 不会自动更新
- 必须重新创建 LLM 实例才能使用新的代理配置

## 🎯 实现 2: LightragServer 的代理回调

**位置**: `knowledge/lightrag_server.py`  
**方法名**: `_register_proxy_change_callback()`  (已统一命名)

### 实现逻辑
1. 后台线程中注册回调 (延迟0.5秒，避免阻塞启动)
2. 定义回调函数 `on_proxy_state_change(proxies)`
3. 回调中:
   - 忽略初始化后2秒内的调用 (避免启动时误触发)
   - 记录代理状态变化日志
   - 如果子进程正在运行:
     * 在后台线程中执行重启
     * 停止子进程
     * 等待端口释放 (最多10秒)
     * 延迟0.2秒
     * 重新启动子进程 (非阻塞)
4. 注册回调，保存 unregister 函数到 `self._proxy_callback_unregister`
5. `stop()` 时调用 unregister

### 为什么需要重启子进程
- 子进程在启动时读取父进程的环境变量
- 父进程后续改变环境变量不会影响已启动的子进程
- 必须重启子进程才能使用新的代理配置

## 📊 两种实现方式对比

| 特性 | MainWindow | LightragServer |
|------|-----------|----------------|
| 方法名 | `_register_proxy_change_callback()` | `_register_proxy_change_callback()` |
| 注册时机 | LLM 初始化后 (同步) | 初始化时 (后台线程+延迟) |
| 初始化保护 | ❌ 无需 | ✅ 2秒保护期 |
| 回调行为 | 重新创建 LLM + 更新 agents | 重启子进程 (后台线程) |
| 执行方式 | 同步执行 (快速完成) | 后台线程 (避免阻塞) |
| Unregister 时机 | `logout()` 方法 | `stop()` 方法 |
| 错误处理 | ✅ 完整 try-except | ✅ 完整 try-except |
| 日志记录 | ✅ 详细日志 | ✅ 详细日志 |

## 🔄 完整工作流程

### 场景 1: 应用启动（代理已配置）

1. **main.py 启动**
   - `init_proxy_after_splash()`
   - ProxyManager 初始化
   - 检测系统代理: `http://127.0.0.1:8888`
   - 测试连接: ✅ 可用
   - 设置环境变量: `HTTP_PROXY=http://127.0.0.1:8888`

2. **MainWindow 初始化**
   - 创建 `self.llm` (`pick_llm`)
   - httpx client 读取环境变量，使用代理
   - `_register_proxy_change_callback()`
   - 注册回调，保存 unregister 函数

3. **LightragServer 启动**
   - 后台线程注册回调 (0.5秒延迟)
   - 启动子进程
   - 子进程继承环境变量，使用代理

4. **ProxyManager 后台监控开始** (每30秒)

### 场景 2: 代理服务停止（运行时）

1. **用户关闭代理软件** (Charles/Fiddler等)

2. **ProxyManager 检测到变化** (最多30秒延迟)
   - 测试连接: ❌ Connection refused
   - 清除环境变量: `del os.environ['HTTP_PROXY']`
   - 触发所有回调: `callback(proxies=None)`

3. **MainWindow 回调被触发**
   - 日志: 🌐 Proxy disabled - using direct connection
   - 调用 `pick_llm()` 重新创建 LLM
   - httpx client 读取环境变量，使用直连
   - 更新 `self.llm`
   - 更新所有 agents 的 `skill_llm`
   - 日志: ✅ LLM recreated successfully

4. **LightragServer 回调被触发**
   - 日志: 🌐 Proxy is now unavailable
   - 后台线程启动
   - 停止子进程
   - 等待端口释放
   - 延迟0.2秒
   - 重启子进程 (子进程读取环境变量，使用直连)
   - 日志: ✅ Subprocess restarted

5. **后续 API 调用使用直连** ✅

### 场景 3: 代理服务重新启动

1. 用户启动代理软件
2. ProxyManager 检测到变化
   - 测试连接: ✅ 可用
   - 设置环境变量: `HTTP_PROXY=http://127.0.0.1:8888`
   - 触发所有回调
3. MainWindow 回调: 重新创建 LLM (使用代理)
4. LightragServer 回调: 重启子进程 (使用代理)
5. 后续 API 调用使用代理 ✅

### 场景 4: 应用退出

1. 用户触发 `logout`
2. `MainWindow._async_cleanup_and_logout()`
   - `self._proxy_callback_unregister()`  # 清理回调
   - 停止 LightragServer
     - `LightragServer.stop()`
     - `self._proxy_callback_unregister()`  # 清理回调
3. ProxyManager 停止监控
4. 应用退出 ✅

## ✅ 设计优势

### 1️⃣ 简单且高效
- 只依赖 ProxyManager 的定时检查
- 无需在 LLM 创建时检查代理（零性能开销）
- 回调机制清晰易懂

### 2️⃣ 自动且可靠
- 自动检测代理变化
- 自动更新所有受影响的组件
- 无需人工干预

### 3️⃣ 统一且可扩展
- 统一的方法命名: `_register_proxy_change_callback()`
- 统一的回调签名
- 易于添加新组件

### 4️⃣ 完整的生命周期管理
- 注册 → 使用 → 清理
- 避免内存泄漏
- 优雅的资源释放

## 🎯 如何添加新组件的代理支持

如果你有新组件需要响应代理变化，按以下模式实现:

```python
class YourComponent:
    """示例组件，展示如何集成代理回调机制"""
    
    def __init__(self):
        # 初始化回调 unregister 函数为 None
        self._proxy_callback_unregister = None
        
        # 注册代理回调
        self._register_proxy_change_callback()
    
    def _register_proxy_change_callback(self):
        """
        Register callback with ProxyManager to handle proxy state changes.
        
        统一方法名: _register_proxy_change_callback()
        """
        try:
            from agent.ec_skills.system_proxy import get_proxy_manager
            
            proxy_manager = get_proxy_manager()
            if not proxy_manager:
                logger.debug("[YourComponent] ProxyManager not available")
                return
            
            def on_proxy_change(proxies):
                """
                Callback fired when proxy state changes.
                
                Args:
                    proxies: None if proxy disabled/unavailable
                            Dict if proxy enabled (e.g. {'http://': '...', ...})
                """
                # 记录日志
                if proxies:
                    proxy_info = f"HTTP: {proxies.get('http://', 'N/A')}"
                    logger.info(f"[YourComponent] 🌐 Proxy enabled - {proxy_info}")
                else:
                    logger.info("[YourComponent] 🌐 Proxy disabled")
                
                # TODO: 实现你的代理变化处理逻辑
                # 例如:
                # - 重新创建 HTTP 客户端
                # - 重启服务
                # - 更新配置
                # etc.
                
                try:
                    self._handle_proxy_change(proxies)
                    logger.info("[YourComponent] ✅ Proxy change handled successfully")
                except Exception as e:
                    logger.error(f"[YourComponent] ❌ Error handling proxy change: {e}")
            
            # 注册回调，保存 unregister 函数
            self._proxy_callback_unregister = proxy_manager.register_callback(
                on_proxy_change
            )
            logger.info("[YourComponent] ✅ Registered proxy change callback")
            
        except Exception as e:
            logger.warning(f"[YourComponent] Failed to register proxy change callback: {e}")
    
    def _handle_proxy_change(self, proxies):
        """
        Handle proxy state change (implement your logic here).
        
        Args:
            proxies: None or Dict
        """
        # 实现具体的处理逻辑
        pass
    
    def cleanup(self):
        """
        Cleanup when component is destroyed.
        
        Important: Always unregister callback to prevent memory leaks!
        """
        # Unregister proxy change callback
        if self._proxy_callback_unregister:
            try:
                self._proxy_callback_unregister()
                self._proxy_callback_unregister = None
                logger.info("[YourComponent] ✅ Proxy change callback unregistered")
            except Exception as e:
                logger.warning(f"[YourComponent] ❌ Error unregistering callback: {e}")
        
        # ... 其他清理逻辑 ...
```

### 关键要点
1. ✅ 使用统一方法名: `_register_proxy_change_callback()`
2. ✅ 保存 unregister 函数到 `self._proxy_callback_unregister`
3. ✅ 在清理/销毁时调用 unregister
4. ✅ 添加详细的日志记录
5. ✅ 使用 try-except 处理异常

## 🐛 常见问题排查

### 问题 1: LLM API 调用失败 "Connection refused"

**症状**:
- API 调用返回 `httpcore.ConnectError: Connection refused`
- 日志显示尝试使用代理: `httpcore/_sync/http_proxy.py`

**原因**:
- 代理服务已停止，但 LLM 实例仍使用旧的代理配置
- httpx client 在初始化时缓存了代理配置

**解决**:
✅ 已通过回调机制自动解决
- ProxyManager 检测到代理不可用
- 清除环境变量
- 触发 MainWindow 回调
- 重新创建 LLM (使用直连)

**验证**:
```
# 检查日志中是否有这些消息
[MainWindow] 🌐 Proxy disabled - using direct connection
[MainWindow] ✅ LLM recreated successfully
```

### 问题 2: LightragServer 子进程仍使用旧代理

**症状**:
- LightragServer 的 API 调用失败
- 主进程环境变量已更新，但子进程未更新

**原因**:
- 子进程在启动时继承父进程环境变量
- 父进程后续修改不影响已启动的子进程

**解决**:
✅ 已通过回调机制自动解决
- ProxyManager 检测到代理变化
- 触发 LightragServer 回调
- 自动重启子进程 (继承新的环境变量)

**验证**:
```
# 检查日志中是否有这些消息
[LightragServer] 🌐 Proxy is now unavailable
[LightragServer] 🔄 Restarting subprocess...
[LightragServer] ✅ Subprocess restarted with new proxy settings
```

### 问题 3: 回调没有被触发

**症状**:
- 代理状态改变，但组件没有响应
- 日志中没有 "Proxy enabled/disabled" 消息

**可能原因**:
1. ProxyManager 未启动
2. 回调注册失败
3. 监控间隔内变化未检测到 (最多30秒延迟)

**排查**:
```
# 1. 检查 ProxyManager 是否启动
[ProxyManager] Starting proxy monitoring...

# 2. 检查回调注册
[MainWindow] ✅ Registered proxy change callback
[LightragServer] ✅ Registered proxy state change callback

# 3. 等待最多30秒，观察是否有检测日志
[ProxyManager] Proxy state changed
```

### 问题 4: 回调导致应用卡顿

**症状**:
- 代理变化时应用短暂卡顿

**原因分析**:
- MainWindow 回调: 同步执行，但很快完成 (< 1秒)
- LightragServer 回调: 后台线程，不阻塞主线程

**如果确实卡顿**:
- 检查 `pick_llm()` 是否耗时过长
- 检查网络连接是否超时
- 考虑将 MainWindow 回调也改为后台线程

### 问题 5: 内存泄漏

**症状**:
- 应用运行时间长后内存持续增长

**可能原因**:
- 回调未 unregister
- ProxyManager 持有已销毁对象的引用

**排查**:
```
# 1. 检查 logout 时是否有 unregister 日志
[MainWindow] ✅ Proxy change callback unregistered

# 2. 检查 LightragServer stop 时是否有 unregister 日志
[LightragServer] ✅ Proxy change callback unregistered

# 3. 确保所有注册的回调都被 unregister
```

## 📝 修改文件清单

本次重构涉及的文件:

1. **gui/MainGUI.py**
   - 添加: `_register_proxy_change_callback()` 方法
   - 修改: `_async_cleanup_and_logout()` - 添加 unregister
   - 行数: 约60行新增

2. **knowledge/lightrag_server.py**
   - 重命名: `_register_proxy_callback()` → `_register_proxy_change_callback()`
   - 更新: 相关注释和日志
   - 行数: 约8处修改

3. **agent/ec_skills/llm_utils/llm_utils.py**
   - 删除: `_check_and_clear_broken_proxy()` 函数 (已撤销)
   - 保持: 原有 LLM 创建逻辑

4. **main.py**
   - 添加: `ECAN_PROXY_ENABLED` 环境变量检查
   - 添加: 代理初始化失败时清除环境变量
   - 行数: 约10行新增

## 🎊 总结

✅ **完整的代理管理系统**
- ProxyManager: 自动检测和更新
- MainWindow: 重新创建 LLM
- LightragServer: 重启子进程

✅ **统一的命名规范**
- `_register_proxy_change_callback()`
- 两个组件使用相同方法名

✅ **完整的生命周期管理**
- 注册回调
- 响应变化
- 清理 unregister

✅ **简单且高效**
- 无需在 LLM 创建时检查代理
- 自动响应代理变化
- 零性能开销

✅ **可扩展的设计**
- 提供通用模式
- 易于添加新组件
- 文档完善

---

**这个系统解决了代理配置变化导致的所有连接问题，同时保持了代码的简洁性和可维护性！** 🚀

