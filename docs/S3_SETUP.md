# S3 Avatar 上传配置指南

> 完整配置指南 - 3步完成配置

---

## ⚡ 快速配置（3步）

### 第1步：配置 Identity Pool（必须）

**作用**：让 User Pool 的 ID Token 可以转换为 AWS 临时凭证

访问：https://console.aws.amazon.com/cognito/v2/identity

```
1. 找到 Identity Pool: us-east-1:ccfa987f-2eee-45c9-ac59-b698f6cbda8e
2. 点击 "User access" 或 "Authentication providers" 标签
3. 在 "Authenticated identities" 部分
4. 点击 "Add authentication provider"
5. 选择 "Cognito user pool"
6. 填写：
   User pool ID:  us-east-1_uUmKJUfB3
   App client ID: 5400r8q5p9gfdhln2feqcpljsh
7. 保存
```

### 第2步：创建 S3 Buckets

**选项A - AWS Console**：
```
访问: https://console.aws.amazon.com/s3/
点击: Create bucket
名称: ecan-avatars
区域: us-east-1
保持默认设置，创建

重复创建:
名称: ecan-skills
区域: us-east-1
```

**选项B - 命令行**：
```bash
aws s3 mb s3://ecan-avatars --region us-east-1
aws s3 mb s3://ecan-skills --region us-east-1
```

### 第3步：配置 IAM 策略（关键）

访问：https://console.aws.amazon.com/iam/

```
1. 左侧菜单: Roles
2. 搜索: Cognito_ecan_Auth_Role  ← 你的认证角色
3. 点击进入角色
4. Permissions 标签
5. Add permissions → Create inline policy
6. 点击 JSON 标签
7. 复制下面的策略内容粘贴
8. Review policy
9. Policy name: eCan-User-S3-Access
10. Create policy
```

**策略内容**（或使用 `iam-policy-s3-access.json`）：

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AllowUserToAccessOwnAvatars",
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:PutObjectAcl",
                "s3:GetObject",
                "s3:GetObjectAcl",
                "s3:DeleteObject"
            ],
            "Resource": [
                "arn:aws:s3:::ecan-avatars/avatars/${cognito-identity.amazonaws.com:sub}/*"
            ]
        },
        {
            "Sid": "AllowUserToAccessOwnSkills",
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:PutObjectAcl",
                "s3:GetObject",
                "s3:GetObjectAcl",
                "s3:DeleteObject"
            ],
            "Resource": [
                "arn:aws:s3:::ecan-skills/skills/${cognito-identity.amazonaws.com:sub}/*"
            ]
        },
        {
            "Sid": "AllowUserToListAvatarsBucket",
            "Effect": "Allow",
            "Action": ["s3:ListBucket"],
            "Resource": ["arn:aws:s3:::ecan-avatars"],
            "Condition": {
                "StringLike": {
                    "s3:prefix": ["avatars/${cognito-identity.amazonaws.com:sub}/*"]
                }
            }
        },
        {
            "Sid": "AllowUserToListSkillsBucket",
            "Effect": "Allow",
            "Action": ["s3:ListBucket"],
            "Resource": ["arn:aws:s3:::ecan-skills"],
            "Condition": {
                "StringLike": {
                    "s3:prefix": ["skills/${cognito-identity.amazonaws.com:sub}/*"]
                }
            }
        },
        {
            "Sid": "AllowUserToGetBucketLocations",
            "Effect": "Allow",
            "Action": ["s3:GetBucketLocation"],
            "Resource": [
                "arn:aws:s3:::ecan-avatars",
                "arn:aws:s3:::ecan-skills"
            ]
        }
    ]
}
```

---

## ✅ 验证配置

配置完成后：

1. **重启应用**
2. **重新登录**
3. **上传 avatar**
4. **查看日志**

### 成功日志：
```log
✅ [AWSCredentials] Got identity ID: us-east-1:xxx...
✅ [AWSCredentials] ✅ Got AWS credentials
✅ [S3Storage] Initialized for bucket: ecan-avatars
✅ [StandardS3Uploader] ✅ Upload successful
✅ [AvatarCloudSync] ✅ Uploaded image to cloud
```

---

## 🐛 故障排查

### 问题1：Token is not from a supported provider

**原因**：Identity Pool 未配置 User Pool

**解决**：完成"第1步：配置 Identity Pool"

---

### 问题2：AccessDenied - s3:PutObject

**日志**：
```
❌ User: arn:aws:sts::xxx:assumed-role/Cognito_ecan_Auth_Role/xxx 
   is not authorized to perform: s3:PutObject
```

**原因**：IAM 策略未配置或路径不匹配

**解决**：
1. 确认已添加 IAM 策略到 `Cognito_ecan_Auth_Role`
2. 策略名称：`eCan-User-S3-Access`
3. 确认路径包含 `avatars/` 前缀：
   ```
   arn:aws:s3:::ecan-avatars/avatars/${cognito-identity.amazonaws.com:sub}/*
   ```

---

### 问题3：NoSuchBucket

**原因**：S3 bucket 不存在

**解决**：创建 `ecan-avatars` 和 `ecan-skills` buckets（第2步）

---

### 问题4：No Identity ID available

**日志**：
```
⚠️ [AvatarCloudSync] No Identity ID available, using username
```

**原因**：Identity Pool 未配置或用户未重新登录

**解决**：
1. 完成"第1步：配置 Identity Pool"
2. 重启应用
3. 重新登录

---

## 📦 S3 架构

```
ecan-avatars/
└── avatars/
    └── {identity-id}/          ← us-east-1:9b535b1b-9dae-c5ff-7c30-19f5f391c615
        ├── images/
        │   ├── hash1.png
        │   └── hash2.jpg
        └── videos/
            └── hash1.webm

ecan-skills/
└── skills/
    └── {identity-id}/
        └── skill.json
```

**路径示例**：
```
s3://ecan-avatars/avatars/us-east-1:9b535b1b-9dae-c5ff-7c30-19f5f391c615/images/abc123.png
s3://ecan-skills/skills/us-east-1:9b535b1b-9dae-c5ff-7c30-19f5f391c615/skill.json
```

---

## 🔑 工作原理

### 认证流程

```
1. 用户登录（Google/Apple）
   ↓
2. Cognito User Pool 返回 ID Token
   ↓
3. Identity Pool 验证 ID Token
   ↓
4. Identity Pool 返回：
   - Identity ID (us-east-1:xxx...)
   - AWS 临时凭证（AccessKey, SecretKey, SessionToken）
   ↓
5. 应用使用临时凭证访问 S3
   ↓
6. IAM 策略检查：用户只能访问自己的目录
   ✓ 允许：avatars/{自己的identity-id}/*
   ✗ 拒绝：avatars/{别人的identity-id}/*
```

### User Pool vs Identity Pool

| 服务 | 作用 | 输入 | 输出 |
|------|------|------|------|
| **User Pool** | 用户认证 | 用户名/密码 | ID Token |
| **Identity Pool** | AWS 授权 | ID Token | Identity ID + AWS 凭证 |

**为什么都需要**：
- User Pool = 护照（证明身份）
- Identity Pool = 签证（允许进入 AWS）
- IAM Policy = 海关（控制能去哪里）

---

## 📝 配置检查清单

- [ ] Identity Pool 已添加 User Pool 认证提供商
- [ ] 创建了 `ecan-avatars` bucket
- [ ] 创建了 `ecan-skills` bucket
- [ ] 在 `Cognito_ecan_Auth_Role` 添加了 `eCan-User-S3-Access` 策略
- [ ] 策略路径包含 `avatars/` 前缀
- [ ] 重启应用
- [ ] 重新登录
- [ ] 日志显示 Identity ID（不是 username）
- [ ] 上传成功

---

## 🎯 常见问题

**Q: 为什么不直接用 User Pool？**
A: User Pool 只负责认证，不能直接访问 AWS 服务。需要 Identity Pool 转换为 AWS 凭证。

**Q: 为什么路径里有 `avatars/` 前缀？**
A: 代码生成的路径格式是 `avatars/{identity-id}/images/file.png`，所以 IAM 策略必须匹配这个格式。

**Q: 可以让用户访问其他用户的文件吗？**
A: 不行。IAM 策略使用 `${cognito-identity.amazonaws.com:sub}` 变量，自动限制每个用户只能访问自己的目录。

**Q: 配置后需要重启吗？**
A: Identity Pool 和 IAM 策略配置后立即生效，但需要重新登录获取新的凭证。

---

**配置完成后，Avatar 自动同步到 S3！** 🎉

