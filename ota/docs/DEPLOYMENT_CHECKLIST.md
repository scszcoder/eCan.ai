# OTA 自动更新部署检查清单

## 部署前准备

### 1. AWS S3 配置 ✓

#### S3 Bucket 创建
- [ ] 创建 S3 bucket (例如: `ecbot-updates`)
- [ ] 选择区域 (推荐: `us-east-1`)
- [ ] 配置 Bucket Policy 或启用 ACL

#### IAM 用户权限
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:PutObjectAcl",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::ecbot-updates/*",
        "arn:aws:s3:::ecbot-updates"
      ]
    }
  ]
}
```

- [ ] IAM 用户已创建
- [ ] 权限策略已附加
- [ ] Access Key 已生成

#### GitHub Secrets 配置
- [ ] `AWS_ACCESS_KEY_ID`
- [ ] `AWS_SECRET_ACCESS_KEY`
- [ ] `S3_BUCKET` (例如: `ecbot-updates`)
- [ ] `AWS_REGION` (例如: `us-east-1`)

---

### 2. 代码签名配置 ✓

#### Windows 签名
- [ ] 获取 Authenticode 签名证书 (.pfx)
- [ ] 配置 GitHub Secret: `WIN_CERT_PFX` (Base64 编码)
- [ ] 配置 GitHub Secret: `WIN_CERT_PASSWORD`

#### macOS 签名
- [ ] 获取 Apple Developer ID 证书 (.p12)
- [ ] 配置 GitHub Secret: `MAC_CERT_P12` (Base64 编码)
- [ ] 配置 GitHub Secret: `MAC_CERT_PASSWORD`
- [ ] 配置 GitHub Secret: `MAC_CODESIGN_IDENTITY`

#### macOS 公证
- [ ] 配置 GitHub Secret: `APPLE_ID`
- [ ] 配置 GitHub Secret: `APPLE_APP_SPECIFIC_PASSWORD`
- [ ] 配置 GitHub Secret: `TEAM_ID`

---

### 3. Ed25519 签名密钥 ✓

#### 生成密钥对
```bash
# 生成私钥
openssl genpkey -algorithm ED25519 -out ed25519_private_key.pem

# 提取公钥
openssl pkey -in ed25519_private_key.pem -pubout -out ed25519_public_key.pem
```

#### 配置
- [ ] 私钥配置到 GitHub Secret: `ED25519_PRIVATE_KEY`
- [ ] 公钥复制到: `ota/certificates/ed25519_public_key.pem`
- [ ] 公钥添加到代码仓库

---

### 4. 版本管理 ✓

- [ ] `VERSION` 文件存在且包含正确版本号
- [ ] 版本号格式: `X.Y.Z` (语义化版本)
- [ ] `config/app_info.py` 可以读取 VERSION 文件

测试命令:
```bash
cat VERSION
python -c "from config.app_info import app_info; print(f'Version: {app_info.version}')"
```

---

## 构建测试

### 5. 本地构建测试 ✓

#### Windows
```bash
# 构建
python build.py --mode prod --platform windows

# 验证输出
ls -la dist/eCan-*-windows-amd64.exe
ls -la dist/eCan-*-windows-amd64-Setup.exe
```

- [ ] 单文件 exe 生成成功
- [ ] Setup.exe 生成成功
- [ ] 文件大小合理 (150-300MB)

#### macOS
```bash
# 构建 amd64
python build.py --mode prod --platform macos --arch amd64

# 构建 aarch64
python build.py --mode prod --platform macos --arch aarch64

# 验证输出
ls -la dist/eCan-*-macos-amd64.pkg
ls -la dist/eCan-*-macos-aarch64.pkg
```

- [ ] amd64 PKG 生成成功
- [ ] aarch64 PKG 生成成功
- [ ] 文件大小合理 (200-400MB)

---

### 6. GitHub Actions 构建测试 ✓

#### 触发构建
```bash
# 方法 1: 推送标签
git tag v1.0.1
git push origin v1.0.1

# 方法 2: 手动触发
# GitHub -> Actions -> Release Build eCan -> Run workflow
```

#### 验证步骤
- [ ] `validate-tag` job 成功
- [ ] `build-windows` job 成功
- [ ] `build-macos` (amd64) job 成功
- [ ] `build-macos` (aarch64) job 成功
- [ ] `upload-to-s3` job 成功
- [ ] `publish-appcast` job 成功

#### 检查输出
- [ ] Windows artifacts 已上传
- [ ] macOS artifacts 已上传
- [ ] S3 文件可以访问
- [ ] Appcast XML 已生成

---

## S3 部署验证

### 7. S3 文件结构验证 ✓

```bash
# 列出 S3 文件
aws s3 ls s3://ecbot-updates/releases/v1.0.1/ --recursive
```

期望的文件结构:
```
releases/
  └── v1.0.1/
      ├── windows/
      │   ├── eCan-1.0.1-windows-amd64.exe
      │   └── eCan-1.0.1-windows-amd64-Setup.exe
      ├── macos/
      │   ├── eCan-1.0.1-macos-amd64.pkg
      │   └── eCan-1.0.1-macos-aarch64.pkg
      ├── checksums/
      │   └── SHA256SUMS
      └── version-metadata.json
```

- [ ] Windows 文件已上传
- [ ] macOS 文件已上传
- [ ] 校验和文件已生成
- [ ] 元数据文件已创建

---

### 8. S3 公共访问验证 ✓

测试文件是否可以公开访问:

```bash
# 测试 Windows Setup.exe
curl -I https://ecbot-updates.s3.us-east-1.amazonaws.com/releases/v1.0.1/windows/eCan-1.0.1-windows-amd64-Setup.exe

# 测试 macOS PKG
curl -I https://ecbot-updates.s3.us-east-1.amazonaws.com/releases/v1.0.1/macos/eCan-1.0.1-macos-amd64.pkg

# 测试 Appcast
curl -I https://ecbot-updates.s3.us-east-1.amazonaws.com/appcast/appcast-windows.xml
curl -I https://ecbot-updates.s3.us-east-1.amazonaws.com/appcast/appcast-macos.xml
```

期望结果: **HTTP 200 OK**

- [ ] Windows Setup.exe 可访问
- [ ] macOS PKG 可访问
- [ ] Appcast XML 可访问
- [ ] 没有 403 Forbidden 错误

---

### 9. Appcast XML 验证 ✓

下载并检查 Appcast 内容:

```bash
# Windows
curl https://ecbot-updates.s3.us-east-1.amazonaws.com/appcast/appcast-windows-amd64.xml

# macOS
curl https://ecbot-updates.s3.us-east-1.amazonaws.com/appcast/appcast-macos-amd64.xml
```

验证内容:
- [ ] XML 格式正确
- [ ] 包含 `<enclosure>` 标签
- [ ] `url` 属性指向正确的 S3 路径
- [ ] `sparkle:version` 正确
- [ ] `sparkle:os` 正确 (windows/macos)
- [ ] `sparkle:arch` 正确 (x86_64/arm64)
- [ ] `sparkle:edSignature` 存在
- [ ] `length` 文件大小正确

---

## 应用端测试

### 10. 更新检测测试 ✓

#### 运行测试脚本
```bash
python tests/test_ota_platforms.py
```

期望输出:
```
✅ 平台检测: 通过
✅ OTA 配置: 通过
✅ 更新器初始化: 通过
✅ 安装器支持: 通过
✅ 更新检查: 发现新版本
✅ 包格式检测: 通过
✅ 签名验证: 通过
```

- [ ] 所有测试通过
- [ ] 无错误或警告

---

### 11. 手动更新测试 ✓

#### Windows 测试
```python
# 在 Windows 机器上运行
from ota.core.updater import OTAUpdater

updater = OTAUpdater()
has_update, info = updater.check_for_updates(return_info=True)

if has_update:
    print(f"发现新版本: {info['latest_version']}")
    
    # 下载更新
    from ota.core.package_manager import package_manager, UpdatePackage
    package = UpdatePackage(
        version=info['latest_version'],
        download_url=info['download_url'],
        file_size=info['file_size'],
        signature=info['signature']
    )
    
    # 下载
    if package_manager.download_package(package):
        print("下载成功")
        
        # 验证
        if package_manager.verify_package(package):
            print("验证成功")
            
            # 安装
            if updater.install_update():
                print("安装成功，即将重启...")
```

- [ ] 可以检测到更新
- [ ] 可以下载更新包
- [ ] 签名验证通过
- [ ] Setup.exe 静默安装成功
- [ ] 应用自动重启
- [ ] 新版本启动成功

#### macOS 测试
```python
# 在 macOS 机器上运行
from ota.core.updater import OTAUpdater

updater = OTAUpdater()
has_update, info = updater.check_for_updates(return_info=True)

if has_update:
    print(f"发现新版本: {info['latest_version']}")
    
    # 下载更新
    from ota.core.package_manager import package_manager, UpdatePackage
    package = UpdatePackage(
        version=info['latest_version'],
        download_url=info['download_url'],
        file_size=info['file_size'],
        signature=info['signature']
    )
    
    # 下载
    if package_manager.download_package(package):
        print("下载成功")
        
        # 验证
        if package_manager.verify_package(package):
            print("验证成功")
            
            # 安装 (需要管理员密码)
            if updater.install_update():
                print("安装成功，即将重启...")
```

- [ ] 可以检测到更新
- [ ] 可以下载更新包
- [ ] 签名验证通过
- [ ] PKG 安装成功（提示输入密码）
- [ ] 应用自动重启
- [ ] 新版本启动成功

---

### 12. GUI 更新对话框测试 ✓

#### 从菜单触发
1. 启动应用
2. 点击菜单: Help -> Check for Updates
3. 等待更新检查完成

- [ ] 更新对话框正常显示
- [ ] 显示当前版本和最新版本
- [ ] 显示更新日志
- [ ] 下载进度条正常工作
- [ ] 安装按钮可用
- [ ] 安装成功后提示重启

---

### 13. 后台自动检查测试 ✓

#### 启用自动检查
```python
# 在应用启动时
from ota.core.updater import OTAUpdater

updater = OTAUpdater()

# 设置回调
def on_update_available(has_update, update_info):
    if has_update:
        print(f"发现新版本: {update_info['latest_version']}")
        # 显示通知或对话框

updater.set_update_callback(on_update_available)

# 启动后台检查 (每小时检查一次)
updater.start_auto_check()
```

- [ ] 后台检查线程启动
- [ ] 定时检查正常工作（每小时）
- [ ] 发现更新时触发回调
- [ ] 不影响应用性能

---

## 错误处理测试

### 14. 网络错误测试 ✓

- [ ] 断网时显示友好错误信息
- [ ] 下载中断后可以重试
- [ ] 超时后自动重试（最多3次）

### 15. 签名验证失败测试 ✓

- [ ] 签名不匹配时拒绝安装
- [ ] 显示安全警告
- [ ] 记录错误日志

### 16. 安装失败测试 ✓

- [ ] 磁盘空间不足时提示
- [ ] 权限不足时提示
- [ ] 安装失败后恢复备份
- [ ] 用户可以重试

---

## 性能测试

### 17. 下载性能 ✓

- [ ] 下载速度合理 (>1MB/s)
- [ ] 进度条更新流畅
- [ ] 可以暂停/取消下载

### 18. 安装性能 ✓

- [ ] Windows Setup.exe 安装时间 < 2 分钟
- [ ] macOS PKG 安装时间 < 2 分钟
- [ ] 重启时间 < 5 秒

---

## 安全测试

### 19. 签名验证 ✓

```bash
# 验证 Ed25519 签名
python -c "
from ota.core.package_manager import PackageManager
from ota.core.package_manager import UpdatePackage
from pathlib import Path

pm = PackageManager()
package = UpdatePackage(
    version='1.0.1',
    download_url='https://...',
    file_size=209715200,
    signature='BASE64_SIGNATURE'
)
package.download_path = Path('eCan-1.0.1-windows-amd64-Setup.exe')
package.is_downloaded = True

result = pm.verify_package(package)
print(f'Verification result: {result}')
"
```

- [ ] 正确的签名验证通过
- [ ] 错误的签名被拒绝
- [ ] 缺少签名时按配置处理

### 20. 文件完整性 ✓

- [ ] SHA256 校验和验证
- [ ] 文件大小验证
- [ ] ZIP/TAR 格式验证
- [ ] 路径遍历检测

---

## 用户体验测试

### 21. 更新通知 ✓

- [ ] 发现更新时显示通知
- [ ] 通知内容清晰（版本号、更新内容）
- [ ] 用户可以选择立即更新或稍后

### 22. 更新进度 ✓

- [ ] 下载进度实时显示
- [ ] 安装进度显示
- [ ] 可以取消操作

### 23. 错误提示 ✓

- [ ] 网络错误提示友好
- [ ] 安装失败提示清晰
- [ ] 提供解决方案或重试选项

---

## 回归测试

### 24. 版本回滚测试 ✓

- [ ] 安装失败后自动回滚
- [ ] 备份文件正确创建
- [ ] 回滚后应用可以正常运行

### 25. 多次更新测试 ✓

- [ ] 从 v1.0.0 更新到 v1.0.1
- [ ] 从 v1.0.1 更新到 v1.0.2
- [ ] 连续更新不会出错

---

## 生产环境部署

### 26. 配置检查 ✓

```bash
# 运行配置验证
python -c "
from ota.core.config import ota_config
if ota_config.validate_config():
    print('✅ 配置验证通过')
else:
    print('❌ 配置验证失败')
"
```

- [ ] 配置验证通过
- [ ] Appcast URL 可访问
- [ ] S3 bucket 可访问

### 27. 监控设置 ✓

- [ ] 设置 S3 访问日志
- [ ] 设置 CloudWatch 告警
- [ ] 监控更新成功率
- [ ] 监控下载流量

### 28. 文档完善 ✓

- [ ] 用户更新指南
- [ ] 故障排查文档
- [ ] 管理员操作手册
- [ ] API 文档

---

## 发布清单

### 29. 发布前检查 ✓

- [ ] 所有测试通过
- [ ] 版本号已更新
- [ ] CHANGELOG 已更新
- [ ] 文档已更新
- [ ] GitHub Secrets 已配置
- [ ] S3 bucket 已配置

### 30. 发布步骤 ✓

1. **更新版本号**
   ```bash
   echo "1.0.1" > VERSION
   git add VERSION
   git commit -m "Bump version to 1.0.1"
   ```

2. **创建标签**
   ```bash
   git tag -a v1.0.1 -m "Release version 1.0.1"
   git push origin v1.0.1
   ```

3. **监控构建**
   - GitHub Actions -> Release Build eCan
   - 等待所有 jobs 完成

4. **验证部署**
   - 检查 S3 文件
   - 测试 Appcast URL
   - 测试应用更新

5. **发布公告**
   - GitHub Release 页面
   - 用户通知邮件
   - 社交媒体

---

## 应急预案

### 31. 回滚计划 ✓

如果新版本有严重问题:

1. **删除 Appcast**
   ```bash
   aws s3 rm s3://ecbot-updates/appcast/appcast-windows.xml
   aws s3 rm s3://ecbot-updates/appcast/appcast-macos.xml
   ```

2. **恢复旧版本 Appcast**
   ```bash
   aws s3 cp s3://ecbot-updates/appcast/backup/appcast-windows-1.0.0.xml \
             s3://ecbot-updates/appcast/appcast-windows.xml --acl public-read
   ```

3. **通知用户**
   - 发布回滚公告
   - 提供手动下载链接

---

## 监控指标

### 32. 关键指标 ✓

- [ ] 更新检查成功率 > 99%
- [ ] 下载成功率 > 95%
- [ ] 安装成功率 > 90%
- [ ] 平均下载时间 < 5 分钟
- [ ] 平均安装时间 < 2 分钟

### 33. 告警设置 ✓

- [ ] S3 可用性告警
- [ ] 下载失败率告警 (> 10%)
- [ ] 安装失败率告警 (> 15%)
- [ ] 签名验证失败告警

---

## 完成标准

所有检查项都勾选 ✓ 后，OTA 系统即可投入生产使用。

**最后更新**: 2025-10-09
**文档版本**: 1.0.0
