# eCan.ai 发布指南

## 📋 目录

- [版本标签格式](#版本标签格式)
- [环境自动检测](#环境自动检测)
- [发布方法](#发布方法)
- [完整发布流程](#完整发布流程)
- [常见场景](#常见场景)
- [注意事项](#注意事项)

---

## 🏷️ 版本标签格式

### **标准格式**

```
v<major>.<minor>.<patch>[-<prerelease>.<number>]
```

### **示例**

| 标签格式 | 说明 | 环境 | Channel |
|---------|------|------|---------|
| `v1.0.0` | 生产版本 | production | stable |
| `v1.2.3` | 生产版本 | production | stable |
| `v2.0.0` | 主版本升级 | production | stable |
| `v1.0.0-rc.1` | 发布候选版本 | staging | stable |
| `v1.0.0-rc.2` | 发布候选版本 2 | staging | stable |
| `v1.0.0-beta.1` | 测试版本 | test | beta |
| `v1.0.0-beta.2` | 测试版本 2 | test | beta |
| `v1.0.0-alpha.1` | 内部测试版本 | development | dev |

---

## 🎯 环境自动检测

工作流会根据 **Git ref** 自动检测目标环境：

### **基于标签的检测**

```bash
v1.0.0           → production  (stable channel)
v1.0.0-rc.1      → staging     (stable channel)
v1.0.0-beta.1    → test        (beta channel)
v1.0.0-alpha.1   → development (dev channel)
```

### **基于分支的检测**

```bash
main / master    → production  (stable channel)
staging          → staging     (stable channel)
develop / dev    → development (dev channel)
其他分支         → development (dev channel)
```

### **版本号计算**

| Git Ref | 计算结果 | 说明 |
|---------|---------|------|
| `v1.0.0` (tag) | `1.0.0` | 直接使用标签版本 |
| `gui-v2` (branch) | `1.0.1-gui-v2-abc1234` | VERSION 文件 + 分支名 + commit hash |
| `main` (branch) | `1.0.1-main-abc1234` | VERSION 文件 + 分支名 + commit hash |

---

## 🚀 发布方法

### **方法 1：创建 Git 标签（推荐用于生产发布）**

```bash
# 1. 确保在正确的分支
git checkout main
git pull origin main

# 2. 更新 VERSION 文件（如果需要）
echo "1.0.0" > VERSION
git add VERSION
git commit -m "Bump version to 1.0.0"
git push origin main

# 3. 创建标签
git tag -a v1.0.0 -m "Release version 1.0.0"

# 4. 推送标签到远程
git push origin v1.0.0

# 5. 工作流会自动触发（如果启用了 push.tags）
# 或者手动触发 GitHub Actions
```

---

### **方法 2：创建 GitHub Release（推荐）**

#### **步骤 1：准备发布**

```bash
# 1. 更新 CHANGELOG
vim CHANGELOG.md
vim CHANGELOG.zh-CN.md

# 2. 更新 VERSION 文件
echo "1.0.0" > VERSION

# 3. 提交更改
git add CHANGELOG.md CHANGELOG.zh-CN.md VERSION
git commit -m "Prepare for v1.0.0 release"
git push origin main
```

#### **步骤 2：创建 Release**

1. 访问：`https://github.com/your-org/eCan.ai/releases/new`
2. 填写信息：
   - **Tag version**: `v1.0.0`
   - **Target**: `main` (或其他分支)
   - **Release title**: `eCan.ai v1.0.0`
   - **Description**: 从 `CHANGELOG.md` 复制内容
3. 选择：
   - ✅ **Set as the latest release** (生产版本)
   - ⬜ **Set as a pre-release** (RC/Beta 版本勾选)
4. 点击 **Publish release**

#### **步骤 3：触发构建**

如果启用了 `release.types: [published]`，工作流会自动触发。

否则需要手动触发：
1. 访问：`Actions → Release Build eCan → Run workflow`
2. 选择：
   - **Use workflow from**: `main`
   - **ref**: `v1.0.0`
   - **platform**: `all`
   - **arch**: `all`
3. 点击 **Run workflow**

---

### **方法 3：手动触发（用于测试或分支构建）**

1. 访问：`Actions → Release Build eCan → Run workflow`
2. 配置参数：
   - **Use workflow from**: 选择工作流来源分支
   - **platform**: `all` / `windows` / `macos`
   - **arch**: `all` / `amd64` / `aarch64`
   - **ref**: 输入构建目标分支名或标签（**留空则自动使用 workflow branch**）
   - **environment**: 选择环境（可选，会自动检测）
   - **channel**: 选择渠道（可选，会自动检测）
3. 点击 **Run workflow**

💡 **提示**：`ref` 参数支持自动同步！
- ✅ **留空**：自动使用 "Use workflow from" 选择的分支
- ✅ **填写**：使用指定的分支/标签（可以与 workflow branch 不同）

#### **参数说明**

**Use workflow from vs ref 的区别：**

| 参数 | 作用 | 示例 |
|------|------|------|
| **Use workflow from** | 使用哪个分支的工作流文件 | `main` = 使用 main 分支的 `.github/workflows/release.yml` |
| **ref** | 构建哪个分支/标签的代码 | `gui-v2` = 构建 gui-v2 分支的代码 |

**常见配置：**

```yaml
# 最简单：自动同步（推荐）
Use workflow from: main
ref: (留空)                              # ✅ 自动使用 main

# 功能分支测试：自动同步（推荐）
Use workflow from: gui-v2
ref: (留空)                              # ✅ 自动使用 gui-v2

# 正常发布：指定标签
Use workflow from: main
ref: v1.0.0                              # ✅ 明确指定标签

# 测试新工作流（特殊情况：两者不同）
Use workflow from: feature/workflow-fix  # 使用新工作流
ref: main                                # 但构建 main 的代码

# 重建旧版本（特殊情况：两者不同）
Use workflow from: main                  # 使用最新工作流
ref: v0.9.0                             # 但构建旧版本代码
```

**建议**：
- ✅ **最简单**：`ref` 留空，自动同步 workflow branch
- ✅ **生产发布**：明确指定标签（如 `v1.0.0`）
- ✅ **分支测试**：`ref` 留空，自动使用功能分支
- ⚠️ **特殊情况**：只在测试工作流修改或重建旧版本时才手动指定不同的 ref

---

## 📝 完整发布流程

### **生产版本发布（v1.0.0）**

```bash
# 1. 切换到 main 分支
git checkout main
git pull origin main

# 2. 更新版本号
echo "1.0.0" > VERSION

# 3. 更新 CHANGELOG
vim CHANGELOG.md
vim CHANGELOG.zh-CN.md

# 添加以下内容：
## [1.0.0] - 2025-11-21
### Added
- 新功能描述
### Fixed
- 修复的问题

# 4. 提交更改
git add VERSION CHANGELOG.md CHANGELOG.zh-CN.md
git commit -m "Release v1.0.0"
git push origin main

# 5. 创建并推送标签
git tag -a v1.0.0 -m "Release version 1.0.0"
git push origin v1.0.0

# 6. 创建 GitHub Release（可选但推荐）
# 访问 GitHub → Releases → New release
# 填写信息并发布

# 7. 验证构建
# 访问 GitHub Actions 查看构建状态
# 检查 S3: s3://ecan-releases/production/releases/v1.0.0/
# 检查 Appcast: https://ecan-releases.s3.us-east-1.amazonaws.com/production/channels/stable/appcast-*.xml
```

---

### **发布候选版本（v1.0.0-rc.1）**

```bash
# 1. 切换到 staging 分支（或 main）
git checkout staging
git pull origin staging

# 2. 更新版本号
echo "1.0.0" > VERSION

# 3. 创建 RC 标签
git tag -a v1.0.0-rc.1 -m "Release candidate 1 for version 1.0.0"
git push origin v1.0.0-rc.1

# 4. 手动触发构建（如果需要）
# Actions → Release Build eCan → Run workflow
# ref: v1.0.0-rc.1
# environment: staging (自动检测)
# channel: stable (自动检测)

# 5. 验证
# 检查 S3: s3://ecan-releases/staging/releases/v1.0.0-rc.1/
# 检查 Appcast: https://ecan-releases.s3.us-east-1.amazonaws.com/staging/channels/stable/appcast-*.xml
```

---

### **测试版本（v1.0.0-beta.1）**

```bash
# 1. 创建 Beta 标签
git tag -a v1.0.0-beta.1 -m "Beta 1 for version 1.0.0"
git push origin v1.0.0-beta.1

# 2. 手动触发构建
# Actions → Release Build eCan → Run workflow
# ref: v1.0.0-beta.1
# environment: test (自动检测)
# channel: beta (自动检测)

# 3. 验证
# 检查 S3: s3://ecan-releases/test/releases/v1.0.0-beta.1/
# 检查 Appcast: https://ecan-releases.s3.us-east-1.amazonaws.com/test/channels/beta/appcast-*.xml
```

---

## 🎬 常见场景

### **场景 1：快速修复（Hotfix）**

```bash
# 1. 从 main 创建 hotfix 分支
git checkout main
git pull origin main
git checkout -b hotfix/fix-critical-bug

# 2. 修复问题
# ... 修改代码 ...

# 3. 提交并推送
git add .
git commit -m "Fix critical bug"
git push origin hotfix/fix-critical-bug

# 4. 测试（手动触发构建）
# Actions → Release Build eCan → Run workflow
# ref: hotfix/fix-critical-bug
# environment: test

# 5. 合并到 main
git checkout main
git merge hotfix/fix-critical-bug
git push origin main

# 6. 创建新版本标签
echo "1.0.1" > VERSION
git add VERSION
git commit -m "Bump version to 1.0.1"
git push origin main

git tag -a v1.0.1 -m "Hotfix release 1.0.1"
git push origin v1.0.1
```

---

### **场景 2：功能分支测试**

```bash
# 1. 在功能分支上开发
git checkout -b feature/new-feature

# 2. 开发完成后，手动触发构建测试
# Actions → Release Build eCan → Run workflow
# ref: feature/new-feature
# environment: development
# platform: all

# 3. 测试通过后合并到 develop
git checkout develop
git merge feature/new-feature
git push origin develop
```

---

### **场景 3：多平台分别构建**

```bash
# 只构建 Windows
# Actions → Release Build eCan → Run workflow
# platform: windows
# arch: amd64

# 只构建 macOS Intel
# Actions → Release Build eCan → Run workflow
# platform: macos
# arch: amd64

# 只构建 macOS Apple Silicon
# Actions → Release Build eCan → Run workflow
# platform: macos
# arch: aarch64
```

---

## ⚠️ 注意事项

### **版本号管理**

1. ✅ **遵循语义化版本**：
   - 主版本号：不兼容的 API 修改
   - 次版本号：向下兼容的功能性新增
   - 修订号：向下兼容的问题修正

2. ✅ **VERSION 文件**：
   - 用于非标签构建的默认版本
   - 应该始终是下一个计划发布的版本
   - 标签构建会覆盖此文件

3. ✅ **标签命名**：
   - 必须以 `v` 开头
   - 使用小写字母（`rc`, `beta`, `alpha`）
   - 预发布版本使用点号分隔（`v1.0.0-rc.1`）

---

### **环境隔离**

| 环境 | 用途 | S3 路径 | Channel | 签名要求 |
|------|------|---------|---------|---------|
| **production** | 生产发布 | `production/` | stable | ✅ 必需 |
| **staging** | 预发布测试 | `staging/` | stable | ✅ 必需 |
| **test** | 功能测试 | `test/` | beta | ✅ 必需 |
| **development** | 开发测试 | `development/` | dev | ❌ 可选 |
| **simulation** | 流程模拟 | `simulation/` | simulation | ✅ 必需 |

---

### **安全要求**

1. ✅ **代码签名**（production/staging）：
   - Windows: Authenticode 签名
   - macOS: Apple 开发者签名 + 公证

2. ✅ **OTA 签名**（test/staging/production）：
   - Ed25519 数字签名
   - 私钥存储在 GitHub Secrets

3. ✅ **环境隔离**：
   - 模拟构建只能上传到 `simulation` 环境
   - 生产构建不包含 `-sim` 版本

---

### **发布检查清单**

#### **发布前**
- [ ] 更新 `VERSION` 文件
- [ ] 更新 `CHANGELOG.md` 和 `CHANGELOG.zh-CN.md`
- [ ] 运行本地测试
- [ ] 代码审查通过
- [ ] 所有 CI 检查通过

#### **发布时**
- [ ] 创建正确格式的标签
- [ ] 推送标签到远程
- [ ] 创建 GitHub Release（推荐）
- [ ] 触发构建工作流

#### **发布后**
- [ ] 验证构建成功
- [ ] 检查 S3 文件上传
- [ ] 验证 Appcast 生成
- [ ] 测试客户端更新
- [ ] 验证签名正确
- [ ] 通知团队

---

## 📚 相关文档

- [CHANGELOG.md](../CHANGELOG.md) - 英文更新日志
- [CHANGELOG.zh-CN.md](../CHANGELOG.zh-CN.md) - 中文更新日志
- [VERSION](../VERSION) - 默认版本号
- [.github/workflows/release.yml](../.github/workflows/release.yml) - 发布工作流
- [.github/workflows/release-simulate.yml](../.github/workflows/release-simulate.yml) - 模拟发布工作流

---

## 🆘 故障排查

### **问题：标签推送后没有触发构建**

**原因**：`release.yml` 中的 `push.tags` 触发器被注释了。

**解决**：手动触发工作流或启用自动触发。

---

### **问题：构建失败，提示签名错误**

**原因**：缺少签名密钥或密钥配置错误。

**解决**：
1. 检查 GitHub Secrets 配置
2. 确认环境需要签名（production/staging/test）
3. 查看构建日志获取详细错误

---

### **问题：客户端获取到错误的版本**

**原因**：Appcast XML 未更新或包含旧版本。

**解决**：
```bash
# 重新生成 appcast
python3 build_system/scripts/generate_appcast.py \
    --env production \
    --channel stable \
    --platform all \
    --arch all
```

---

## 📞 联系支持

如有问题，请：
1. 查看 [GitHub Actions 日志](https://github.com/your-org/eCan.ai/actions)
2. 检查 [Issues](https://github.com/your-org/eCan.ai/issues)
3. 联系开发团队
