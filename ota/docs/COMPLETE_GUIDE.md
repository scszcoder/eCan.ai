# OTA 自动更新完整指南

## 🎯 系统概述

eCan 应用的 OTA (Over-The-Air) 自动更新系统已完全实现，支持 **Windows EXE** 和 **macOS PKG** 的全自动更新流程。

### 支持的平台和格式

| 平台 | 支持格式 | 推荐格式 | 状态 |
|------|---------|---------|------|
| Windows | EXE, MSI | Setup.exe | ✅ 已实现 |
| macOS | PKG, DMG | PKG | ✅ 已实现 |
| Linux | AppImage, DEB, RPM | AppImage | 🚧 计划中 |

---

## 📋 快速开始

### 1. 配置 GitHub Secrets

在 GitHub 仓库设置中添加以下 secrets:

```
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
S3_BUCKET=ecbot-updates
AWS_REGION=us-east-1
ED25519_PRIVATE_KEY=your_private_key
WIN_CERT_PFX=your_windows_cert_base64
WIN_CERT_PASSWORD=your_cert_password
MAC_CERT_P12=your_mac_cert_base64
MAC_CERT_PASSWORD=your_cert_password
MAC_CODESIGN_IDENTITY=your_identity
APPLE_ID=your_apple_id
APPLE_APP_SPECIFIC_PASSWORD=your_app_password
TEAM_ID=your_team_id
```

### 2. 触发构建

```bash
# 更新版本号
echo "1.0.1" > VERSION
git add VERSION
git commit -m "Bump version to 1.0.1"

# 创建标签
git tag -a v1.0.1 -m "Release version 1.0.1"
git push origin v1.0.1
```

### 3. 验证部署

```bash
# 检查 S3 文件
aws s3 ls s3://ecbot-updates/releases/v1.0.1/ --recursive

# 测试 Appcast
curl https://ecbot-updates.s3.us-east-1.amazonaws.com/appcast/appcast-windows.xml
curl https://ecbot-updates.s3.us-east-1.amazonaws.com/appcast/appcast-macos.xml

# 运行测试
python3 tests/test_ota_platforms.py
```

---

## 🔄 完整更新流程

### Windows 更新流程

```
用户启动应用
  ↓
后台检查更新 (每小时)
  ↓
从 S3 下载 Appcast XML
  ↓
解析 XML，发现新版本 (1.0.1 > 1.0.0)
  ↓
显示更新通知
  ↓
用户点击"更新"
  ↓
下载 Setup.exe (优先) 或单文件 exe
  ↓
验证 Ed25519 签名 + SHA256 校验和
  ↓
静默安装: Setup.exe /S
  ↓
创建重启脚本 (restart.bat)
  ↓
退出当前应用
  ↓
脚本延迟 3 秒后启动新版本
  ↓
新版本启动，显示"已更新到 v1.0.1"
  ↓
清理临时文件和脚本
```

### macOS 更新流程

```
用户启动应用
  ↓
后台检查更新 (每小时)
  ↓
从 S3 下载 Appcast XML
  ↓
解析 XML，发现新版本 (1.0.1 > 1.0.0)
  ↓
显示更新通知
  ↓
用户点击"更新"
  ↓
下载 PKG 文件
  ↓
验证 Ed25519 签名 + SHA256 校验和
  ↓
请求管理员权限 (AppleScript 对话框)
  ↓
安装: installer -pkg eCan.pkg -target /
  ↓
创建重启脚本 (restart.sh)
  ↓
退出当前应用
  ↓
脚本延迟 3 秒后启动新版本
  ↓
新版本启动，显示"已更新到 v1.0.1"
  ↓
清理临时文件和脚本
```

---

## 🛠️ 技术实现

### 核心组件

#### 1. OTAUpdater (`ota/core/updater.py`)
```python
class OTAUpdater:
    def check_for_updates(silent=False, return_info=False)  # 检查更新
    def install_update()                                     # 安装更新
    def start_auto_check()                                   # 启动后台检查
    def stop_auto_check()                                    # 停止后台检查
    def set_update_callback(callback)                        # 设置回调
```

**特性**:
- ✅ 线程安全
- ✅ 平台自动检测
- ✅ 自动选择适配器 (Sparkle/WinSparkle/Generic)
- ✅ 版本比较
- ✅ 架构匹配 (amd64/aarch64)

#### 2. PackageManager (`ota/core/package_manager.py`)
```python
class PackageManager:
    def download_package(package, progress_callback, max_retries=3)  # 下载
    def verify_package(package, public_key_path)                     # 验证
    def install_package(package, install_dir)                        # 安装
    def cleanup()                                                    # 清理
```

**安全特性**:
- ✅ 下载重试 (指数退避，最多 3 次)
- ✅ SHA256 哈希验证
- ✅ Ed25519/RSA-PSS 签名验证
- ✅ ZIP/TAR 格式验证
- ✅ 路径遍历检测
- ✅ 文件大小限制 (1GB)
- ✅ 备份和回滚机制

#### 3. InstallationManager (`ota/core/installer.py`)
```python
class InstallationManager:
    def install_package(package_path, install_options)  # 安装入口
    def restart_application(delay_seconds=3)            # 重启应用
    def restore_backup()                                # 恢复备份
    def cleanup_backup()                                # 清理备份
```

**Windows 支持**:
```python
def _install_exe(self, package_path, install_options):
    """安装 Windows EXE"""
    cmd = [str(package_path), '/S']  # 静默安装
    subprocess.run(cmd, timeout=300)

def _install_msi(self, package_path, install_options):
    """安装 Windows MSI"""
    cmd = ["msiexec", "/i", str(package_path), "/quiet", "/norestart"]
    subprocess.run(cmd, timeout=300)
```

**macOS 支持**:
```python
def _install_pkg(self, package_path, install_options):
    """安装 macOS PKG"""
    # 使用 AppleScript 请求管理员权限
    applescript = f'''
    do shell script "installer -pkg {package_path} -target /" with administrator privileges
    '''
    subprocess.run(["osascript", "-e", applescript], timeout=300)

def _install_dmg(self, package_path, install_options):
    """安装 macOS DMG"""
    # 挂载 DMG
    subprocess.run(["hdiutil", "attach", str(package_path)])
    # 复制 .app 到 /Applications
    shutil.copytree(app_file, "/Applications/eCan.app")
    # 卸载 DMG
    subprocess.run(["hdiutil", "detach", mount_point])
```

---

## 📦 GitHub Actions 构建流程

### Windows 构建
```yaml
build-windows:
  runs-on: windows-latest
  steps:
    - name: Build with PyInstaller
      run: python build.py --mode prod --platform windows
    
    - name: Sign EXE
      run: signtool sign /f cert.pfx /p ${{ secrets.WIN_CERT_PASSWORD }} dist/*.exe
    
    - name: Create Inno Setup installer
      run: iscc build_system/windows_installer.iss
    
    - name: Upload artifacts
      uses: actions/upload-artifact@v4
      with:
        path: |
          dist/eCan-*-windows-amd64.exe
          dist/eCan-*-windows-amd64-Setup.exe
```

### macOS 构建
```yaml
build-macos:
  runs-on: macos-latest
  strategy:
    matrix:
      arch: [amd64, aarch64]
  steps:
    - name: Build with PyInstaller
      run: python build.py --mode prod --platform macos --arch ${{ matrix.arch }}
    
    - name: Code sign
      run: codesign --deep --force --options runtime --sign "$MAC_CODESIGN_IDENTITY" dist/eCan.app
    
    - name: Create PKG
      run: pkgbuild --root dist/eCan.app --install-location /Applications/eCan.app dist/eCan.pkg
    
    - name: Notarize
      run: xcrun notarytool submit dist/eCan.pkg --wait
    
    - name: Staple
      run: xcrun stapler staple dist/eCan.pkg
```

### S3 上传
```yaml
upload-to-s3:
  needs: [build-windows, build-macos]
  steps:
    - name: Upload to S3
      run: |
        aws s3 sync upload/ s3://$S3_BUCKET/releases/v$VERSION/ \
          --acl public-read \
          --cache-control "max-age=31536000"
```

### Appcast 生成
```yaml
publish-appcast:
  needs: upload-to-s3
  steps:
    - name: Generate Appcast
      run: python build_system/generate_appcast.py
    
    - name: Sign with Ed25519
      run: python build_system/sign_appcast.py
    
    - name: Upload to S3
      run: |
        aws s3 sync dist/appcast/ s3://$S3_BUCKET/appcast/ \
          --acl public-read \
          --cache-control "max-age=300"
```

---

## 🔐 安全机制

### 1. 代码签名

#### Windows Authenticode
```bash
# 签名 EXE
signtool sign /f certificate.pfx /p password /t http://timestamp.digicert.com dist/eCan.exe
```

#### macOS Code Signing
```bash
# 签名 app bundle
codesign --deep --force --options runtime \
  --sign "Developer ID Application: Your Name (TEAM_ID)" \
  dist/eCan.app

# 公证
xcrun notarytool submit dist/eCan.pkg \
  --apple-id "your@email.com" \
  --password "app-specific-password" \
  --team-id "TEAM_ID" --wait

# 装订
xcrun stapler staple dist/eCan.pkg
```

### 2. Ed25519 数字签名

```python
# 生成密钥对
from cryptography.hazmat.primitives.asymmetric import ed25519

private_key = ed25519.Ed25519PrivateKey.generate()
public_key = private_key.public_key()

# 签名
signature = private_key.sign(file_data)

# 验证
public_key.verify(signature, file_data)
```

### 3. HTTPS 传输

所有更新文件通过 HTTPS 下载:
```
https://ecbot-updates.s3.us-east-1.amazonaws.com/releases/v1.0.1/...
```

---

## 📊 配置说明

### OTA 配置 (`ota/core/config.py`)

```python
{
  "use_local_server": false,
  "remote_server_url": "https://updates.ecbot.com",
  "check_interval": 3600,  # 1 小时
  "auto_check": true,
  "silent_mode": false,
  "signature_verification": true,
  "signature_required": true,
  
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
      # S3 作为更新源
      "appcast_url": "https://ecbot-updates.s3.us-east-1.amazonaws.com/appcast/appcast-windows.xml",
      "appcast_urls": {
        "amd64": "https://ecbot-updates.s3.us-east-1.amazonaws.com/appcast/appcast-windows-amd64.xml"
      }
    }
  }
}
```

---

## 🧪 测试指南

### 运行完整测试

```bash
# 平台支持测试
python3 tests/test_ota_platforms.py

# 期望输出:
# ✅ 平台检测: 通过
# ✅ OTA 配置: 通过
# ✅ 更新器初始化: 通过
# ✅ 安装器支持: 通过
# ✅ 更新检查: 发现新版本
# ✅ 包格式检测: 通过
# ✅ 签名验证: 通过
```

### 手动测试更新

```python
from ota.core.updater import OTAUpdater

# 初始化
updater = OTAUpdater()

# 检查更新
has_update, info = updater.check_for_updates(return_info=True)

if has_update:
    print(f"发现新版本: {info['latest_version']}")
    print(f"下载 URL: {info['download_url']}")
    
    # 安装更新
    if updater.install_update():
        print("更新成功，即将重启...")
```

---

## 📈 监控和统计

### S3 访问日志

```bash
# 启用 S3 访问日志
aws s3api put-bucket-logging \
  --bucket ecbot-updates \
  --bucket-logging-status '{
    "LoggingEnabled": {
      "TargetBucket": "ecbot-logs",
      "TargetPrefix": "s3-access-logs/"
    }
  }'
```

### CloudWatch 告警

```bash
# 创建下载失败率告警
aws cloudwatch put-metric-alarm \
  --alarm-name ota-download-failure-rate \
  --metric-name DownloadFailureRate \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold
```

---

## 🚀 部署清单

使用 [OTA_DEPLOYMENT_CHECKLIST.md](./OTA_DEPLOYMENT_CHECKLIST.md) 确保所有步骤完成。

### 关键检查项

- [ ] AWS S3 bucket 已创建并配置
- [ ] GitHub Secrets 已配置
- [ ] 代码签名证书已配置
- [ ] Ed25519 密钥对已生成
- [ ] VERSION 文件存在
- [ ] 本地构建测试通过
- [ ] GitHub Actions 构建测试通过
- [ ] S3 文件可以公开访问
- [ ] Appcast XML 格式正确
- [ ] 应用可以检测到更新
- [ ] 下载和验证正常
- [ ] 安装和重启正常

---

## 📚 相关文档

1. **[OTA 系统分析报告](./OTA_SYSTEM_ANALYSIS.md)**
   - 完整的系统架构分析
   - 已实现功能清单
   - 存在的问题和修复方案

2. **[OTA 修复总结](./OTA_FIXES_SUMMARY.md)**
   - P0/P1 问题修复详情
   - 代码变更清单
   - 测试建议

3. **[OTA 平台支持](./OTA_PLATFORM_SUPPORT.md)**
   - Windows/macOS 平台详细说明
   - 安装流程和代码示例
   - 常见问题解决方案

4. **[S3 配置指南](./S3_BUCKET_POLICY_SETUP.md)**
   - S3 bucket 配置步骤
   - IAM 权限设置
   - CloudFront CDN 配置

5. **[部署检查清单](./OTA_DEPLOYMENT_CHECKLIST.md)**
   - 33 项详细检查项
   - 测试步骤
   - 应急预案

---

## 🆘 故障排查

### Windows

**问题**: Setup.exe 安装失败
```
解决方案:
1. 以管理员身份运行
2. 检查防病毒软件是否阻止
3. 查看日志: %TEMP%\eCan-Setup.log
```

**问题**: 下载失败 (403 Forbidden)
```
解决方案:
1. 检查 S3 文件 ACL: aws s3api get-object-acl --bucket ecbot-updates --key releases/v1.0.1/windows/eCan.exe
2. 添加 --acl public-read 到上传命令
3. 或配置 Bucket Policy
```

### macOS

**问题**: PKG 安装提示"已损坏"
```
解决方案:
1. 检查代码签名: codesign -dv --verbose=4 eCan.pkg
2. 检查公证状态: xcrun stapler validate eCan.pkg
3. 重新签名和公证
```

**问题**: 权限不足
```
解决方案:
1. 确保使用 AppleScript "with administrator privileges"
2. 或在终端使用 sudo
3. 检查 /Applications 目录权限
```

---

## 🔮 未来计划

### 高优先级
1. **增量更新**: 只下载变更的文件
2. **更新回滚**: 自动回滚失败的更新
3. **错误上报**: 收集更新失败的详细信息

### 中优先级
4. **CDN 加速**: 使用 CloudFront 分发
5. **更新统计**: 收集更新成功率数据
6. **Linux 支持**: 添加 AppImage/DEB/RPM 支持

### 低优先级
7. **差分更新**: 二进制差分补丁
8. **P2P 分发**: 减少服务器带宽
9. **离线更新**: 支持本地更新包

---

## 📞 支持

如有问题或建议:
- GitHub Issues: https://github.com/scszcoder/ecbot/issues
- 邮件: support@ecbot.com
- 文档: https://docs.ecbot.com/ota

---

**最后更新**: 2025-10-09 20:38
**文档版本**: 1.0.0
**系统状态**: ✅ 生产就绪
