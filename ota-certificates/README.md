# ECBot OTA证书和签名配置

## 📁 目录结构

```
ota-certificates/
├── keys/                    # Ed25519密钥文件
│   ├── ed25519_private_key.pem
│   └── ed25519_public_key.pem
├── certificates/            # 平台代码签名证书
│   ├── windows/            # Windows证书
│   └── macos/              # macOS证书
├── scripts/                # 证书转换脚本
│   ├── convert_windows_cert.ps1
│   └── convert_macos_cert.sh
├── configs/                # GitHub Secrets配置
│   ├── github_secrets.json
│   └── github_secrets_complete.json
└── docs/                   # 配置指南
    ├── github_secrets_guide.json
    ├── windows_signing_guide.json
    └── macos_signing_guide.json
```

## 🚀 快速开始

1. **设置基本OTA签名**：
   ```bash
   # 复制configs/github_secrets.json中的ED25519_PRIVATE_KEY到GitHub Secrets
   ```

2. **转换Windows证书**：
   ```powershell
   # 使用scripts/convert_windows_cert.ps1
   ```

3. **转换macOS证书**：
   ```bash
   # 使用scripts/convert_macos_cert.sh
   ```

## 📚 相关文档

- [GitHub Secrets配置指南](../GITHUB_SECRETS_SETUP.md)
- [完整签名配置指南](../SIGNING_SETUP_GUIDE.md)
- [证书购买指南](../CERTIFICATE_PURCHASE_GUIDE.md)

## ⚠️ 安全提醒

- 私钥文件仅用于本地测试
- 生产环境请使用GitHub Secrets
- 定期轮换Ed25519密钥
- 不要将私钥提交到版本控制
