# ECBot OTA 快速开始指南

## 🎯 一分钟启用OTA功能

### 步骤1：设置GitHub Secret
在GitHub仓库中添加以下Secret：

1. 进入 **Settings** → **Secrets and variables** → **Actions**
2. 点击 **New repository secret**
3. 设置：
   ```
   名称: ED25519_PRIVATE_KEY
   值: LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0tCk1DNENBUUF3QlFZREsyVndCQ0lFSVAxRUtZVnhvY0p5M1JTSVZlSFVMTm11UGFNcGtFa3o5ckNvQWpta0RaUSsKLS0tLS1FTkQgUFJJVkFURSBLRVktLS0tLQo=
   ```

### 步骤2：验证配置
1. 推送代码或手动触发GitHub Actions
2. 检查CI日志中的"Generate appcast"步骤
3. 确认没有签名相关错误

**🎉 完成！您的OTA功能现在已启用！**

## 📁 重要文件位置

```
ota/
├── README.md              # 完整OTA文档
├── SIGNING_SETUP.md       # 详细签名配置
├── QUICK_START.md         # 本文件（快速开始）
└── platforms/             # 平台特定配置
    ├── SPARKLE_SETUP.md   # macOS配置
    └── WINSPARKLE_SETUP.md # Windows配置

ota-certificates/          # 签名文件和配置
├── keys/                  # Ed25519密钥
├── configs/               # GitHub配置
└── scripts/               # 证书转换脚本
```

## 🔐 签名状态

| 签名类型 | 状态 | 说明 |
|---------|------|------|
| **Ed25519 OTA签名** | ✅ 已配置 | 必需，确保更新安全 |
| **Windows代码签名** | ⏳ 可选 | 避免安全警告，需购买证书 |
| **macOS代码签名** | ⏳ 可选 | 避免安全警告，需Apple Developer |

## 💡 下一步（可选）

### 配置Windows代码签名
1. 购买Windows代码签名证书（~$200-474/年）
2. 使用转换脚本：`ota-certificates/scripts/convert_windows_cert.ps1`
3. 设置GitHub Secrets：`WIN_CERT_PFX`、`WIN_CERT_PASSWORD`

### 配置macOS代码签名
1. 注册Apple Developer Program（$99-299/年）
2. 使用转换脚本：`ota-certificates/scripts/convert_macos_cert.sh`
3. 设置GitHub Secrets：`MAC_CERT_P12`、`APPLE_ID`等

## 🔧 测试OTA功能

```bash
# 运行OTA测试
python ota/test_ota.py

# 启动测试服务器
python ota/server/update_server.py
```

## 📞 需要帮助？

- **完整文档**: [ota/README.md](README.md)
- **签名配置**: [ota/SIGNING_SETUP.md](SIGNING_SETUP.md)
- **Windows平台**: [ota/platforms/WINSPARKLE_SETUP.md](platforms/WINSPARKLE_SETUP.md)
- **macOS平台**: [ota/platforms/SPARKLE_SETUP.md](platforms/SPARKLE_SETUP.md)

---

**🚀 您的ECBot现在具备安全的OTA更新能力！**
