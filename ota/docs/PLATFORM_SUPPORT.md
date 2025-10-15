# OTA 平台支持说明

## 支持的平台和格式

### ✅ Windows 平台

#### 支持的安装包格式
1. **Setup.exe (推荐)** - Inno Setup 安装器
   - 文件名: `eCan-{version}-windows-amd64-Setup.exe`
   - 优点: 支持覆盖安装、卸载、开始菜单快捷方式
   - 静默安装参数: `/S`, `/SILENT`, `/VERYSILENT`

2. **单文件 EXE** - PyInstaller 单文件
   - 文件名: `eCan-{version}-windows-amd64.exe`
   - 优点: 便携、无需安装
   - 缺点: 无法实现平滑升级（需要替换运行中的文件）

3. **MSI 安装包**
   - 文件名: `eCan-{version}-windows-amd64.msi`
   - 静默安装: `msiexec /i package.msi /quiet /norestart`

#### OTA 更新流程
```
1. 检测更新 (从 S3 Appcast)
   ↓
2. 下载 Setup.exe (优先) 或 单文件 exe
   ↓
3. 验证 Ed25519 签名
   ↓
4. 静默安装
   - Setup.exe: 自动执行 /S 参数
   - 单文件 exe: 替换当前文件（需要重启）
   ↓
5. 自动重启应用
```

#### 代码实现
```python
# ota/core/installer.py

def _install_exe(self, package_path: Path, install_options: Dict[str, Any]) -> bool:
    """安装Windows EXE包"""
    cmd = [str(package_path)]
    
    # 静默安装参数
    if install_options.get('silent', True):
        cmd.extend(['/S'])  # Inno Setup 静默参数
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return result.returncode == 0
```

---

### ✅ macOS 平台

#### 支持的安装包格式
1. **PKG 安装包 (推荐)** - macOS 标准安装器
   - 文件名: `eCan-{version}-macos-{amd64|aarch64}.pkg`
   - 优点: 系统原生支持、支持签名和公证
   - 安装位置: `/Applications/eCan.app`

2. **DMG 磁盘镜像**
   - 文件名: `eCan-{version}-macos-{amd64|aarch64}.dmg`
   - 需要手动拖拽到 Applications 文件夹
   - OTA 支持: 自动挂载、复制、卸载

#### OTA 更新流程
```
1. 检测更新 (从 S3 Appcast)
   ↓
2. 下载 PKG 文件
   ↓
3. 验证 Ed25519 签名
   ↓
4. 请求管理员权限
   - 交互式: sudo installer
   - GUI: AppleScript "with administrator privileges"
   ↓
5. 安装到 /Applications
   ↓
6. 自动重启应用
```

#### 代码实现
```python
# ota/core/installer.py

def _install_pkg(self, package_path: Path, install_options: Dict[str, Any]) -> bool:
    """安装macOS PKG包"""
    
    # 方法 1: 使用 AppleScript (GUI 环境)
    if install_options.get('silent', False) or not sys.stdin.isatty():
        applescript = f'''
        do shell script "installer -pkg {package_path} -target /" with administrator privileges
        '''
        result = subprocess.run(["osascript", "-e", applescript], 
                              capture_output=True, text=True, timeout=300)
    else:
        # 方法 2: 使用 sudo (终端环境)
        cmd = ["sudo", "installer", "-pkg", str(package_path), "-target", "/"]
        result = subprocess.run(cmd, timeout=300)
    
    return result.returncode == 0
```

---
## 完整的 OTA 配置

### Appcast URL 配置

```python
# ota/core/config.py

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

## Appcast XML 示例

### Windows Appcast
```xml
<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
  <channel>
    <title>eCan Windows Updates</title>
    <item>
      <title>Version 1.0.1</title>
      <pubDate>Wed, 09 Oct 2025 12:00:00 +0000</pubDate>
      <enclosure 
        url="https://ecbot-updates.s3.us-east-1.amazonaws.com/releases/v1.0.1/windows/eCan-1.0.1-windows-amd64-Setup.exe"
        sparkle:version="1.0.1"
        sparkle:os="windows"
        sparkle:arch="x86_64"
        length="209715200"
        type="application/octet-stream"
        sparkle:edSignature="BASE64_SIGNATURE_HERE"
      />
      <description><![CDATA[
        <h2>What's New</h2>
        <ul>
          <li>New feature 1</li>
          <li>Bug fixes</li>
        </ul>
      ]]></description>
    </item>
  </channel>
</rss>
```

### macOS Appcast
```xml
<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
  <channel>
    <title>eCan macOS Updates</title>
    <item>
      <title>Version 1.0.1</title>
      <pubDate>Wed, 09 Oct 2025 12:00:00 +0000</pubDate>
      <enclosure 
        url="https://ecbot-updates.s3.us-east-1.amazonaws.com/releases/v1.0.1/macos/eCan-1.0.1-macos-amd64.pkg"
        sparkle:version="1.0.1"
        sparkle:os="macos"
        sparkle:arch="x86_64"
        length="314572800"
        type="application/octet-stream"
        sparkle:edSignature="BASE64_SIGNATURE_HERE"
      />
      <description><![CDATA[
        <h2>What's New</h2>
        <ul>
          <li>New feature 1</li>
          <li>Bug fixes</li>
        </ul>
      ]]></description>
    </item>
  </channel>
</rss>
```

---

## GitHub Actions 构建流程

### Windows 构建
```yaml
# .github/workflows/release.yml

build-windows:
  runs-on: windows-latest
  steps:
    - name: Build with PyInstaller
      run: python build.py --mode prod --platform windows
    
    - name: Create Inno Setup installer
      run: |
        # 生成 Setup.exe
        iscc build_system/windows_installer.iss
    
    - name: Upload artifacts
      uses: actions/upload-artifact@v4
      with:
        name: eCan-Windows-${{ needs.validate-tag.outputs.version }}
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
    
    - name: Code sign app bundle
      run: |
        codesign --deep --force --options runtime \
          --sign "$MAC_CODESIGN_IDENTITY" "dist/eCan.app"
    
    - name: Create PKG installer
      run: |
        pkgbuild --root dist/eCan.app \
          --identifier com.ecbot.ecan \
          --version $VERSION \
          --install-location /Applications/eCan.app \
          dist/eCan-$VERSION-macos-${{ matrix.arch }}.pkg
    
    - name: Notarize PKG
      run: |
        xcrun notarytool submit dist/eCan-*.pkg \
          --apple-id "$APPLE_ID" \
          --password "$APPLE_APP_SPECIFIC_PASSWORD" \
          --team-id "$TEAM_ID" --wait
```

---

## 测试指南

### Windows 测试

#### 1. 测试 Setup.exe 安装
```powershell
# 静默安装
.\eCan-1.0.1-windows-amd64-Setup.exe /S

# 验证安装
Get-ItemProperty HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\* | 
  Where-Object {$_.DisplayName -like "*eCan*"}
```

#### 2. 测试 OTA 更新
```python
# test_windows_ota.py
from ota.core.updater import OTAUpdater

updater = OTAUpdater()
has_update, info = updater.check_for_updates(return_info=True)

if has_update:
    print(f"New version available: {info['latest_version']}")
    print(f"Download URL: {info['download_url']}")
    
    # 下载并安装
    updater.install_update()
```

### macOS 测试

#### 1. 测试 PKG 安装
```bash
# 安装 PKG
sudo installer -pkg eCan-1.0.1-macos-amd64.pkg -target /

# 验证安装
ls -la /Applications/eCan.app
pkgutil --pkgs | grep com.ecbot.ecan
```

#### 2. 测试 OTA 更新
```python
# test_macos_ota.py
from ota.core.updater import OTAUpdater

updater = OTAUpdater()
has_update, info = updater.check_for_updates(return_info=True)

if has_update:
    print(f"New version available: {info['latest_version']}")
    print(f"Download URL: {info['download_url']}")
    
    # 下载并安装
    updater.install_update()
```

---

## 常见问题

### Windows

**Q: Setup.exe 安装失败，返回错误代码 1**
```
A: 检查是否有管理员权限，或者尝试手动运行：
   右键 -> 以管理员身份运行
```

**Q: 单文件 exe 无法更新自己**
```
A: 这是 Windows 的限制，运行中的 exe 无法被替换。
   解决方案：
   1. 使用 Setup.exe (推荐)
   2. 或者创建临时脚本，退出后替换文件
```

**Q: 防火墙阻止下载**
```
A: 添加 S3 域名到白名单：
   *.s3.us-east-1.amazonaws.com
```

### macOS

**Q: PKG 安装需要输入密码**
```
A: 这是正常的，PKG 需要管理员权限。
   在 GUI 环境中，会自动弹出密码对话框。
```

**Q: "eCan.app 已损坏" 或 "无法打开"**
```
A: 需要进行代码签名和公证：
   1. 代码签名: codesign --deep --force --options runtime
   2. 公证: xcrun notarytool submit
   3. 装订: xcrun stapler staple
```

**Q: 更新后应用无法启动**
```
A: 检查权限：
   sudo chmod -R 755 /Applications/eCan.app
   sudo xattr -cr /Applications/eCan.app
```

---

## 安全最佳实践

### 1. 代码签名
- **Windows**: 使用 Authenticode 签名证书
- **macOS**: 使用 Apple Developer ID 证书

### 2. 数字签名验证
```python
# 所有更新包都使用 Ed25519 签名
signature = sign_update(package_path)  # 构建时签名
verify_package(package, public_key)    # 安装前验证
```

### 3. HTTPS 传输
- 所有 URL 必须使用 HTTPS
- S3 bucket 配置 SSL/TLS

### 4. 权限最小化
- Windows: 只请求必要的管理员权限
- macOS: 使用 AppleScript 请求权限，而不是 setuid

---

## 性能优化

### 1. 增量更新（未来）
```python
# 只下载变更的文件
delta_package = create_delta(old_version, new_version)
apply_delta(current_app, delta_package)
```

### 2. 断点续传
```python
# 支持大文件下载中断后继续
download_with_resume(url, local_path, resume_from=bytes_downloaded)
```

### 3. CDN 加速
```
使用 CloudFront 分发更新包：
- 全球加速
- 降低 S3 成本
- 更好的可用性
```

---

## 监控和统计

### 更新成功率
```python
# 记录更新事件
log_update_event({
    "version": "1.0.1",
    "platform": "windows",
    "status": "success",
    "duration": 45.2,  # 秒
    "timestamp": "2025-10-09T12:00:00Z"
})
```

### 错误追踪
```python
# 上报更新错误
report_update_error({
    "error_code": "SIGNATURE_INVALID",
    "version": "1.0.1",
    "platform": "macos",
    "details": error_details
})
```

---

## 相关文档

- [OTA 系统分析报告](./OTA_SYSTEM_ANALYSIS.md)
- [OTA 修复总结](./OTA_FIXES_SUMMARY.md)
- [S3 配置指南](./S3_BUCKET_POLICY_SETUP.md)
- [GitHub Actions Workflow](../.github/workflows/release.yml)

---

**最后更新**: 2025-10-09
**文档版本**: 1.0.0
