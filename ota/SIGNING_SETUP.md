# ECBot OTA签名配置指南

## 🎯 快速开始

### 立即可用的配置
只需在GitHub仓库中设置一个Secret即可启用OTA功能：

```
名称: ED25519_PRIVATE_KEY
值: LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0tCk1DNENBUUF3QlFZREsyVndCQ0lFSVAxRUtZVnhvY0p5M1JTSVZlSFVMTm11UGFNcGtFa3o5ckNvQWpta0RaUSsKLS0tLS1FTkQgUFJJVkFURSBLRVktLS0tLQo=
```

**🎉 设置后OTA功能即可正常工作！**

## 📁 签名文件位置

```
ota-certificates/
├── keys/                    # Ed25519密钥文件
├── configs/                 # GitHub Secrets配置
├── scripts/                 # 证书转换脚本
└── certificates/            # 平台证书存放
```

## 🔐 签名层次说明

| 签名类型 | 状态 | 作用 | 必需性 |
|---------|------|------|--------|
| **Ed25519签名** | ✅ 已配置 | OTA更新安全验证 | **必需** |
| **Windows代码签名** | ⏳ 可选 | 避免Windows安全警告 | 可选 |
| **macOS代码签名** | ⏳ 可选 | 避免macOS安全警告 | 可选 |

## 💰 证书购买建议

### 个人开发者
- **Ed25519**: 免费（已配置）
- **Windows**: Sectigo ~$200/年
- **macOS**: Apple Developer $99/年

### 企业用户
- **Ed25519**: 免费（已配置）
- **Windows**: DigiCert ~$474/年
- **macOS**: Apple Developer $299/年

## 🛠️ 证书配置

### Windows证书
1. 购买Windows代码签名证书
2. 使用转换脚本：
   ```powershell
   .\ota-certificates\scripts\convert_windows_cert.ps1
   ```
3. 设置GitHub Secrets：
   - `WIN_CERT_PFX`: 证书Base64编码
   - `WIN_CERT_PASSWORD`: 证书密码

### macOS证书
1. 注册Apple Developer Program
2. 使用转换脚本：
   ```bash
   ./ota-certificates/scripts/convert_macos_cert.sh
   ```
3. 设置GitHub Secrets：
   - `MAC_CERT_P12`: 证书Base64编码
   - `MAC_CERT_PASSWORD`: 证书密码
   - `MAC_CODESIGN_IDENTITY`: 代码签名身份
   - `APPLE_ID`: Apple ID邮箱
   - `APPLE_APP_SPECIFIC_PASSWORD`: App专用密码
   - `TEAM_ID`: Apple Developer Team ID

## 🔄 OTA工作原理

### 有签名（推荐）
```
用户 → 检查更新 → 下载更新包 → 验证Ed25519签名 → 安装更新
                                    ✅ 安全可靠
```

### 无签名（不推荐）
```
用户 → 检查更新 → 下载更新包 → 直接安装
                              ⚠️ 存在风险
```

## ✅ 验证清单

- [ ] 设置`ED25519_PRIVATE_KEY` GitHub Secret
- [ ] 触发CI构建，检查"Generate appcast"步骤
- [ ] 验证appcast.xml生成成功
- [ ] 测试客户端OTA更新功能
- [ ] （可选）配置Windows代码签名
- [ ] （可选）配置macOS代码签名和公证

## 🛡️ 安全提醒

- ✅ 私钥已安全存储在GitHub Secrets中
- ⚠️ 不要将私钥提交到版本控制
- 🔄 建议每年轮换Ed25519密钥对
- 📅 定期检查证书过期时间

## 📞 故障排除

### 签名验证失败
- 检查`ED25519_PRIVATE_KEY`是否正确设置
- 验证密钥格式（Base64编码的PEM）
- 检查cryptography库版本

### Windows签名失败
- 验证证书格式和密码
- 检查证书是否过期
- 确认signtool.exe可用

### macOS签名失败
- 检查所有Apple凭据
- 验证证书是否正确
- 确认网络连接正常

---

**🎉 恭喜！您的ECBot现在已具备安全的OTA更新能力！**
