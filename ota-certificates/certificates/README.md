# 平台代码签名证书

## 目录结构

```
certificates/
├── windows/          # Windows代码签名证书
│   ├── production/   # 生产环境证书
│   └── test/         # 测试证书
└── macos/            # macOS开发者证书
    ├── production/   # 生产环境证书
    └── test/         # 测试证书
```

## 证书类型

### Windows证书
- `.pfx` 文件：包含私钥的证书
- 需要密码保护
- 用于签名.exe和.msi文件

### macOS证书
- `.p12` 文件：开发者证书
- 需要密码保护
- 用于代码签名和公证

## 使用脚本转换

### Windows
```powershell
../scripts/convert_windows_cert.ps1
```

### macOS
```bash
../scripts/convert_macos_cert.sh
```

## ⚠️ 重要提醒

- 证书文件包含敏感信息，不要提交到版本控制
- 使用Base64编码存储在GitHub Secrets中
- 定期检查证书过期时间
