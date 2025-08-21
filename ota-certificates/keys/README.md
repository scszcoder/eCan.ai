# Ed25519密钥文件

## 文件说明

- `ed25519_private_key.pem`: Ed25519私钥（仅本地测试使用）
- `ed25519_public_key.pem`: Ed25519公钥（客户端验证使用）

## 使用方法

### 设置GitHub Secret
```bash
# 将configs/github_secrets.json中的ED25519_PRIVATE_KEY值
# 设置到GitHub仓库的Secrets中
```

### 客户端配置
```python
# 将公钥内容配置到客户端
PUBLIC_KEY_PEM = '''-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAZw1gpG5ADlGgbf2OJHKfSCXwJ9yKfMzhOm9h+w9lNK4=
-----END PUBLIC KEY-----'''
```

## ⚠️ 安全注意

- 私钥文件不要提交到版本控制
- 生产环境使用GitHub Secrets存储私钥
- 建议每年轮换一次密钥对
