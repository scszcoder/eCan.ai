# OTA 自动更新工作流程详解

## 📋 完整流程概览

```
开发者推送标签
    ↓
GitHub Actions 构建
    ├→ 构建 Windows (EXE + Setup.exe)
    ├→ 构建 macOS (PKG amd64 + aarch64)
    ├→ 代码签名和公证
    └→ 上传到 S3 (--acl public-read)
    ↓
生成 Appcast XML
    ├→ 解析 S3 文件列表
    ├→ 优先选择 Setup.exe (Windows)
    ├→ Ed25519 签名
    └→ 上传到 S3
    ↓
应用启动
    ├→ 初始化 OTAUpdater
    ├→ 读取当前版本 (VERSION 文件)
    └→ 启动后台检查 (每小时)
    ↓
检查更新
    ├→ 下载 Appcast XML (S3)
    ├→ 解析 XML 获取最新版本
    ├→ 比较版本号
    └→ 显示更新对话框
    ↓
下载更新
    ├→ 下载安装包 (支持重试)
    ├→ SHA256 哈希验证
    └→ Ed25519 签名验证
    ↓
安装更新
    ├→ Windows: Setup.exe /S (静默安装)
    ├→ macOS: installer -pkg (AppleScript 请求权限)
    └→ 重启应用 (3秒延迟)
```

---

## 1. 构建发布流程

### 触发构建

```bash
# 1. 更新版本号
echo "1.0.1" > VERSION

# 2. 创建并推送标签
git tag -a v1.0.1 -m "Release 1.0.1"
git push origin v1.0.1
```

### GitHub Actions 工作流

**文件**: `.github/workflows/release.yml`

#### 关键步骤：

1. **验证标签** → 确保格式正确 (v1.0.0)
2. **构建 Windows** → 生成 EXE + Setup.exe
3. **构建 macOS** → 生成 PKG (amd64 + aarch64)
4. **上传 S3** → 使用 `--acl public-read`
5. **生成 Appcast** → 创建 XML 并签名

**输出文件**:
```
s3://ecbot-updates/
├── releases/v1.0.1/
│   ├── windows/
│   │   ├── eCan-1.0.1-windows-amd64.exe
│   │   └── eCan-1.0.1-windows-amd64-Setup.exe  ← 优先
│   ├── macos/
│   │   ├── eCan-1.0.1-macos-amd64.pkg
│   │   └── eCan-1.0.1-macos-aarch64.pkg
│   └── checksums/SHA256SUMS
└── appcast/
    ├── appcast-windows-amd64.xml
    └── appcast-macos-amd64.xml
```

---

## 2. 应用启动和检查流程

### 初始化

**文件**: `ota/core/updater.py`

```python
class OTAUpdater:
    def __init__(self):
        # 1. 检测平台 (Darwin/Windows)
        self.platform = platform.system()
        
        # 2. 读取当前版本 (从 VERSION 文件)
        self.app_version = app_info.version  # "1.0.0"
        
        # 3. 获取 Appcast URL
        self.appcast_url = ota_config.get_appcast_url()
        # S3: https://ecbot-updates.s3.us-east-1.amazonaws.com/appcast/...
        # 备份: https://scszcoder.github.io/ecbot/appcast-...
```

### 后台检查

```python
def start_auto_check(self):
    """启动后台自动检查 (每小时)"""
    self._auto_check_thread = threading.Thread(
        target=self._auto_check_loop,
        args=(3600,),  # 3600秒 = 1小时
        daemon=True
    )
    self._auto_check_thread.start()
```

### 检查更新

```python
def check_for_updates(self):
    # 1. 下载 Appcast XML (S3 → GitHub Pages 备份)
    appcast_xml = self._download_appcast()
    
    # 2. 解析 XML
    latest_version, download_url, file_size, signature = self._parse_appcast(appcast_xml)
    
    # 3. 比较版本
    if latest_version > self.app_version:
        # 4. 显示更新对话框
        self._show_update_dialog()
        return True
    
    return False
```

---

## 3. 下载更新流程

### 下载包

**文件**: `ota/core/package_manager.py`

```python
def download_package(self, package, progress_callback=None, max_retries=3):
    """下载更新包 (支持重试)"""
    
    for attempt in range(max_retries):
        try:
            # 1. 流式下载
            response = requests.get(package.download_url, stream=True)
            
            # 2. 写入文件并报告进度
            with open(download_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    progress_callback(downloaded, total_size)
            
            return True
            
        except Exception as e:
            # 3. 指数退避重试
            wait_time = 2 ** attempt
            time.sleep(wait_time)
```

### 验证包

```python
def verify_package(self, package):
    """验证更新包"""
    
    # 1. SHA256 哈希验证
    sha256_hash = hashlib.sha256()
    with open(package.download_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256_hash.update(chunk)
    
    # 2. Ed25519 签名验证
    public_key = load_pem_public_key(public_key_path.read_bytes())
    signature_bytes = base64.b64decode(package.signature)
    file_data = package.download_path.read_bytes()
    
    public_key.verify(signature_bytes, file_data)
    
    return True
```

---

## 4. 安装更新流程

### Windows 安装

**文件**: `ota/core/installer.py`

```python
def _install_exe(self, package_path, install_options):
    """安装 Windows EXE"""
    
    if 'setup' in package_path.name.lower():
        # Setup.exe: 静默安装
        cmd = [str(package_path), '/S']
        subprocess.run(cmd, timeout=300)
    else:
        # 单文件 EXE: 替换当前执行文件
        current_exe = Path(sys.executable)
        shutil.copy2(package_path, current_exe)
```

### macOS 安装

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

### 重启应用

```python
def restart_application(self, delay_seconds=3):
    """重启应用"""
    
    if sys.platform == 'darwin':
        # macOS: 使用 open 命令
        script = f'''
        sleep {delay_seconds}
        open -a "{app_path}"
        '''
        subprocess.Popen(['sh', '-c', script])
        
    elif sys.platform == 'win32':
        # Windows: 使用批处理脚本
        script = f'''
        @echo off
        timeout /t {delay_seconds} /nobreak
        start "" "{app_path}"
        '''
        subprocess.Popen(['cmd', '/c', script])
    
    # 退出当前应用
    sys.exit(0)
```

---

## 5. 完整时序图

```
开发者                GitHub Actions           S3                应用              用户
  │                        │                  │                 │                │
  │ 1. git push v1.0.1     │                  │                 │                │
  ├────────────────────────>│                  │                 │                │
  │                        │                  │                 │                │
  │                        │ 2. 构建 Win/Mac   │                 │                │
  │                        │ 3. 代码签名       │                 │                │
  │                        │                  │                 │                │
  │                        │ 4. 上传文件       │                 │                │
  │                        ├─────────────────>│                 │                │
  │                        │                  │                 │                │
  │                        │ 5. 生成 Appcast   │                 │                │
  │                        ├─────────────────>│                 │                │
  │                        │                  │                 │                │
  │                        │                  │  6. 启动应用     │                │
  │                        │                  │<────────────────┤                │
  │                        │                  │                 │                │
  │                        │                  │  7. 后台检查     │                │
  │                        │                  │  (每小时)        │                │
  │                        │                  │                 │                │
  │                        │                  │  8. 下载 Appcast │                │
  │                        │                  ├────────────────>│                │
  │                        │                  │                 │                │
  │                        │                  │  9. 发现新版本   │                │
  │                        │                  │                 │                │
  │                        │                  │                 │ 10. 显示通知   │
  │                        │                  │                 ├───────────────>│
  │                        │                  │                 │                │
  │                        │                  │                 │ 11. 点击"更新" │
  │                        │                  │                 │<───────────────┤
  │                        │                  │                 │                │
  │                        │                  │ 12. 下载安装包   │                │
  │                        │                  ├────────────────>│                │
  │                        │                  │                 │                │
  │                        │                  │ 13. 验证签名     │                │
  │                        │                  │                 │                │
  │                        │                  │ 14. 安装         │                │
  │                        │                  │                 │                │
  │                        │                  │ 15. 重启应用     │                │
  │                        │                  │                 │                │
  │                        │                  │ 16. 新版本启动   │                │
  │                        │                  │<────────────────┤                │
```

---

## 6. 关键配置文件

### VERSION 文件

```
1.0.0
```

### ota/core/config.py

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
        "appcast_url": "https://ecbot-updates.s3.us-east-1.amazonaws.com/appcast/appcast-windows.xml",
        "appcast_urls": {
            "amd64": "https://ecbot-updates.s3.us-east-1.amazonaws.com/appcast/appcast-windows-amd64.xml"
        }
    }
}
```

---

## 7. 安全机制

### 多层验证

1. **代码签名**
   - Windows: Authenticode
   - macOS: Apple Developer ID + 公证

2. **传输加密**
   - HTTPS 强制加密

3. **文件验证**
   - SHA256 哈希
   - Ed25519 数字签名

4. **权限控制**
   - Windows: 管理员权限
   - macOS: AppleScript 权限对话框

---

## 8. 错误处理

### 网络错误

- 自动重试 (最多 3 次)
- 指数退避 (2^n 秒)
- 下载失败提示用户

### 验证失败

- 签名不匹配 → 拒绝安装
- 哈希不匹配 → 重新下载
- 文件损坏 → 显示错误

### 安装失败

- 磁盘空间不足 → 提示用户
- 权限不足 → 请求权限
- 安装错误 → 恢复备份

---

## 9. 性能指标

| 阶段 | 时间 |
|------|------|
| 更新检查 | < 2 秒 |
| 下载 (200MB) | ~3 分钟 (1 MB/s) |
| 验证 | < 5 秒 |
| 安装 | < 2 分钟 |
| 重启 | < 5 秒 |
| **总计** | **~6 分钟** |

---

**文档版本**: 1.0.0  
**最后更新**: 2025-10-10
