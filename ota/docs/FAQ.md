# OTA 系统常见问题 (FAQ)

## 📋 目录

1. [平台支持](#平台支持)
2. [配置问题](#配置问题)
3. [更新流程](#更新流程)
4. [错误处理](#错误处理)

---

## 平台支持

### Q1: OTA 系统支持哪些安装包格式？

**A**: 完整支持列表：

#### Windows
- ✅ **Setup.exe** (推荐) - 安装器，支持静默安装
- ✅ **单文件 EXE** - 便携版，直接替换
- ✅ **MSI** - 企业级部署

#### macOS
- ✅ **PKG** (推荐) - 系统原生支持，自动安装到 /Applications
- ✅ **DMG** - 磁盘镜像，支持拖拽安装

#### Linux
- 🚧 **AppImage** (计划中)
- 🚧 **DEB/RPM** (计划中)

---

### Q2: Appcast XML 生成是否支持 macOS PKG？

**A**: ✅ **完全支持**

**代码位置**: `build_system/generate_appcast.py` 第 119-121 行

```python
if platform_filter == 'macos':
    if not (name.endswith('.pkg') or name.endswith('.dmg') or 'macos' in name or 'darwin' in name):
        continue
```

**支持的文件**:
- `eCan-1.0.0-macos-amd64.pkg` ✅
- `eCan-1.0.0-macos-aarch64.pkg` ✅
- `eCan-1.0.0-macos.dmg` ✅

**生成的 Appcast 示例**:

```xml
<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
  <channel>
    <title>eCan AI Assistant</title>
    <item>
      <title>eCan 1.0.0</title>
      <sparkle:version>1.0.0</sparkle:version>
      <enclosure
        url="https://ecbot-updates.s3.us-east-1.amazonaws.com/releases/v1.0.0/macos/eCan-1.0.0-macos-amd64.pkg"
        sparkle:version="1.0.0"
        sparkle:os="macos"
        sparkle:arch="x86_64"
        length="209715200"
        type="application/octet-stream"
        sparkle:edSignature="MC0CFQ..." />
    </item>
  </channel>
</rss>
```

---

## 配置问题

### Q3: 更新源配置

**A**: ✅ **使用 AWS S3 作为单一更新源**

**当前配置** (`ota/core/config.py`):

```python
"platforms": {
    "darwin": {
        # S3 作为更新源
        "appcast_url": "https://ecbot-updates.s3.us-east-1.amazonaws.com/appcast/appcast-macos.xml",
        "appcast_urls": {
            "amd64": "https://ecbot-updates.s3.us-east-1.amazonaws.com/appcast/appcast-macos-amd64.xml",
            "aarch64": "https://ecbot-updates.s3.us-east-1.amazonaws.com/appcast/appcast-macos-aarch64.xml"
        }
    },
    "windows": {
        "appcast_url": "https://ecbot-updates.s3.us-east-1.amazonaws.com/appcast/appcast-windows.xml"
    }
}
```

**实际行为**:
- ✅ 从 S3 下载 Appcast XML
- ✅ 从 S3 下载安装包
- ✅ 自动重试 3 次（指数退避）
- ❌ 下载失败后提示用户

**高可用建议**:
- 配置 CloudFront CDN 加速
- 启用 S3 跨区域复制
- 监控 S3 可用性

---

### Q4: 如何提高更新源的可靠性？

**A**: 多种方案可选

**方案 1: CloudFront CDN** (推荐)

```python
# 配置 CloudFront 域名
"appcast_url": "https://cdn.ecbot.com/appcast/appcast-macos.xml"
```

**优点**:
- ✅ 全球加速
- ✅ 自动缓存
- ✅ 高可用性
- ✅ 降低 S3 成本

**方案 2: S3 跨区域复制**

- 主区域: us-east-1
- 备份区域: us-west-2
- 自动同步

**方案 3: 多源 fallback** (需要开发)

- 实现自动切换逻辑
- 配置多个备份源
- 智能选择最快源

---

## 更新流程

### Q5: 更新检查的完整流程是什么？

**A**: 完整流程如下：

```
1. 应用启动
   ├→ 初始化 OTAUpdater
   ├→ 读取当前版本 (VERSION 文件)
   └→ 启动后台检查 (每小时)

2. 检查更新
   ├→ 下载 Appcast XML (S3)
   ├→ 解析 XML 获取最新版本
   ├→ 比较版本号
   └→ 显示更新对话框 (如果有新版本)

3. 下载更新
   ├→ 下载安装包 (支持重试 3 次)
   ├→ SHA256 哈希验证
   └→ Ed25519 签名验证

4. 安装更新
   ├→ Windows: Setup.exe /S (静默安装)
   ├→ macOS: installer -pkg (AppleScript 请求权限)
   └→ 重启应用 (3秒延迟)
```

**详细说明**: 参见 [WORKFLOW.md](./WORKFLOW.md)

---

### Q6: 为什么优先使用 Setup.exe 而不是单文件 EXE？

**A**: Setup.exe 提供更好的用户体验

**对比**:

| 特性 | Setup.exe | 单文件 EXE |
|------|-----------|-----------|
| 安装位置 | Program Files | 任意位置 |
| 开始菜单 | ✅ 自动创建 | ❌ 需手动 |
| 卸载程序 | ✅ 标准卸载 | ❌ 手动删除 |
| 注册表 | ✅ 正确注册 | ❌ 无注册 |
| 更新体验 | ✅ 覆盖安装 | ⚠️ 替换文件 |
| 企业部署 | ✅ 支持 | ⚠️ 受限 |

**代码实现**: `build_system/generate_appcast.py` 第 98-109 行

```python
# Prioritize Setup.exe
if 'setup' in name and name.endswith('.exe'):
    setup_files.append(asset)
elif name.endswith('.exe'):
    standalone_files.append(asset)

# Use Setup.exe if available, otherwise use standalone exe
if setup_files:
    filtered.extend(setup_files)
else:
    filtered.extend(standalone_files)
```

---

## 错误处理

### Q7: 如果 S3 下载失败怎么办？

**A**: 当前行为和建议

**当前行为**:
1. 自动重试 3 次
2. 使用指数退避 (2^n 秒)
3. 所有重试失败后报错

**代码**: `ota/core/package_manager.py`

```python
for attempt in range(max_retries):  # max_retries = 3
    try:
        response = requests.get(package.download_url, stream=True, timeout=30)
        # ... 下载逻辑
        return True
    except Exception as e:
        if attempt < max_retries - 1:
            wait_time = 2 ** attempt  # 1s, 2s, 4s
            time.sleep(wait_time)
```

**建议改进**:
1. 实现 GitHub Pages 备份（见 Q4）
2. 配置 CloudFront CDN 加速
3. 增加更详细的错误提示

---

### Q8: 签名验证失败会怎样？

**A**: 根据配置决定

**配置项**: `ota/core/config.py`

```python
"signature_verification": True,   # 是否启用验证
"signature_required": True,       # 验证失败是否阻止安装
```

**行为**:

| 配置 | 行为 |
|------|------|
| `signature_verification: True` + `signature_required: True` | ❌ 拒绝安装 |
| `signature_verification: True` + `signature_required: False` | ⚠️ 警告但继续 |
| `signature_verification: False` | ✅ 跳过验证 |

**生产环境建议**: 
```python
"signature_verification": True,
"signature_required": True
```

**代码**: `ota/core/package_manager.py`

```python
try:
    public_key.verify(signature_bytes, file_data)
    logger.info("Signature verification passed")
except Exception as e:
    logger.error(f"Signature verification failed: {e}")
    
    if ota_config.get('signature_required', True):
        return False  # 阻止安装
```

---

### Q9: macOS PKG 安装需要管理员权限吗？

**A**: ✅ 是的，自动请求

**实现方式**: 使用 AppleScript 请求权限

**代码**: `ota/core/installer.py`

```python
def _install_pkg(self, package_path, install_options):
    """安装 macOS PKG"""
    
    # 使用 AppleScript 请求管理员权限
    applescript = f'''
    do shell script "installer -pkg {package_path} -target /" with administrator privileges
    '''
    
    result = subprocess.run(["osascript", "-e", applescript], timeout=300)
    return result.returncode == 0
```

**用户体验**:
1. 应用调用安装
2. 系统弹出权限对话框
3. 用户输入密码
4. 自动安装到 /Applications

**优点**:
- ✅ 系统原生对话框
- ✅ 用户熟悉的流程
- ✅ 安全可靠

---

### Q10: 如何测试 OTA 更新流程？

**A**: 使用本地测试服务器

**步骤**:

1. **启动本地服务器**:
   ```bash
   cd ota
   python test_local_ota.py
   ```

2. **配置应用使用本地服务器**:
   ```python
   from ota.core.config import ota_config
   ota_config.set_use_local_server(True)
   ```

3. **触发更新检查**:
   ```python
   from ota.core.updater import OTAUpdater
   updater = OTAUpdater()
   updater.check_for_updates()
   ```

**详细说明**: 参见 [QUICK_START.md](../QUICK_START.md)

---

## 性能问题

### Q11: 更新检查会影响应用性能吗？

**A**: ❌ 不会，后台线程运行

**实现**:

```python
# 后台线程，不阻塞主线程
self._auto_check_thread = threading.Thread(
    target=self._auto_check_loop,
    args=(3600,),  # 每小时检查一次
    daemon=True    # 守护线程，应用退出时自动结束
)
self._auto_check_thread.start()
```

**性能指标**:

| 操作 | 时间 | 影响 |
|------|------|------|
| 更新检查 | < 2 秒 | 无感知 |
| 下载 (200MB) | ~3 分钟 | 后台进行 |
| 验证 | < 5 秒 | 无感知 |
| 安装 | < 2 分钟 | 需要重启 |

---

### Q12: 如何减少更新包大小？

**A**: 几种优化方案

1. **增量更新** (计划中)
   - 只下载变更的文件
   - 可减少 60-80% 下载量

2. **压缩优化**
   - 使用 UPX 压缩 EXE
   - 优化资源文件

3. **差分更新** (计划中)
   - 二进制差分
   - 只传输差异部分

**当前**: 全量更新
**未来**: 增量 + 差分更新

---

## 安全问题

### Q13: OTA 更新安全吗？

**A**: ✅ 多层安全保障

**安全机制**:

1. **代码签名**
   - Windows: Authenticode
   - macOS: Apple Developer ID + 公证

2. **传输加密**
   - HTTPS 强制加密
   - TLS 1.2+

3. **文件验证**
   - SHA256 哈希
   - Ed25519 数字签名
   - 文件大小验证

4. **权限控制**
   - Windows: 管理员权限
   - macOS: AppleScript 权限对话框

**详细说明**: 参见 [COMPLETE_GUIDE.md](./COMPLETE_GUIDE.md#安全机制)

---

### Q14: Ed25519 私钥如何管理？

**A**: GitHub Secrets 安全存储

**设置步骤**:

1. **生成密钥对**:
   ```bash
   python ota/build/sparkle/generate_keys.py
   ```

2. **添加到 GitHub Secrets**:
   - 设置名称: `ED25519_PRIVATE_KEY`
   - 值: 私钥内容（PEM 格式）

3. **公钥部署**:
   - 位置: `ota/certificates/ed25519_public_key.pem`
   - 打包到应用中

**安全建议**:
- ❌ 不要提交私钥到代码库
- ✅ 使用 GitHub Secrets
- ✅ 定期轮换密钥
- ✅ 限制访问权限

---

## 更多问题？

如果您的问题未在此列出，请：

1. 查看 [完整文档](./README.md)
2. 提交 [GitHub Issue](https://github.com/scszcoder/ecbot/issues)
3. 发送邮件到 support@ecbot.com

---

**最后更新**: 2025-10-11  
**文档版本**: 1.0.0
