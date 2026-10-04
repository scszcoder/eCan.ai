# Release Environment & Channel Guide

## 📋 概述

本文档说明 eCan.ai 项目的发布环境（Environment）和更新渠道（Channel）的标准映射关系。

## 🎯 核心概念

### Environment（部署环境级别）

决定代码质量标准和部署位置：

- **production**: 生产环境 - 最高质量标准，面向所有用户
- **staging**: 预发布环境 - 生产前最后验证
- **test**: 测试环境 - 内部测试
- **development**: 开发环境 - 开发和调试

### Channel（更新渠道）

决定更新频率和稳定性：

- **stable**: 稳定版本 - 经过充分测试，推荐所有用户使用
- **beta**: 测试版本 - 功能完整，可能有 bug，适合尝鲜用户
- **nightly**: 每日构建 - 最新功能，来自 main 分支，适合开发者
- **dev**: 开发版本 - 不稳定，仅供开发测试

## 📊 标准映射表

| Git Ref | Environment | Channel | S3 Path | 说明 |
|---------|------------|---------|---------|------|
| **Tags** | | | | |
| `v1.0.0` | `production` | `stable` | `production/channels/stable/` | ✅ 正式发布 |
| `v1.0.0-rc.1` | `production` | `beta` | `production/channels/beta/` | ✅ 候选版本 |
| `v1.0.0-beta.1` | `staging` | `beta` | `staging/channels/beta/` | 公开测试 |
| `v1.0.0-alpha.1` | `test` | `dev` | `test/channels/dev/` | 内部测试 |
| **Branches** | | | | |
| `main/master` | `production` | `nightly` | `production/channels/nightly/` | ✅ **每日构建** |
| `staging` | `staging` | `stable` | `staging/channels/stable/` | 预发布验证 |
| `develop/dev` | `development` | `dev` | `development/channels/dev/` | 开发分支 |
| `feature/*` | `development` | `dev` | `development/channels/dev/` | 功能分支 |

## 🔑 关键设计原则

### 为什么 main/master 是 production environment？

1. **代码质量标准**：main 分支应该始终保持生产级别的代码质量
2. **CI/CD 最佳实践**：main = production-ready code
3. **行业标准**：与 Chrome、VS Code、Firefox 等主流软件一致
4. **渠道分离**：通过 channel 区分稳定性，而不是通过 environment

### Production 环境的三个渠道

```
production/
├── channels/
│   ├── stable/          ← v1.0.0 tags (所有用户)
│   ├── beta/            ← v1.0.0-rc.1 tags (测试用户)
│   └── nightly/         ← main/master branch (开发者)
```

**关键点**：
- 三个渠道互不干扰，各自独立的 appcast.xml
- stable 和 nightly 都在 production 环境，但用户群不同
- 通过订阅不同渠道，用户可以选择更新频率

## 🛡️ 保护规则

### 1. production/stable 渠道保护

```yaml
⚠️  ONLY 正式版本 tag (v1.0.0) 可以部署
⚠️  任何分支（包括 main/master）都不能部署到 stable channel
⚠️  防止意外覆盖稳定版本
```

### 2. production/nightly 渠道

```yaml
✅ 只接受 main/master 分支
✅ 每次提交自动构建
✅ 不会影响 stable channel
```

### 3. 其他环境

- **staging**: 接受 staging 分支和 beta/rc tags
- **test**: 接受 alpha tags 和测试分支
- **development**: 接受所有开发分支

## 📝 使用示例

### 场景 1: 发布正式版本 (Stable Release)

```bash
git tag v1.0.0
git push origin v1.0.0
```

**结果**：
- Environment: `production`
- Channel: `stable`
- S3 Path: `production/channels/stable/appcast-*.xml`
- 用户群：所有用户（默认更新渠道）

### 场景 2: 发布候选版本 (Release Candidate)

```bash
git tag v1.0.0-rc.1
git push origin v1.0.0-rc.1
```

**结果**：
- Environment: `production`
- Channel: `beta`
- S3 Path: `production/channels/beta/appcast-*.xml`
- 用户群：测试用户

### 场景 3: main/master 分支每日构建 (Nightly Build)

```bash
git push origin main
```

**结果**：
- Environment: `production`
- Channel: `nightly`
- S3 Path: `production/channels/nightly/appcast-*.xml`
- 用户群：开发者、尝鲜用户
- 说明：自动触发，无需手动操作

### 场景 4: 测试新功能 (Feature Branch)

```bash
# 在 GitHub Actions 界面手动触发
# ref: feature/new-ui
# environment: auto
# channel: auto
```

**结果**：
- Environment: `development`
- Channel: `dev`
- S3 Path: `development/channels/dev/appcast-*.xml`
- 用户群：内部开发测试

### 场景 5: 预发布验证 (Staging)

```bash
git push origin staging
```

**结果**：
- Environment: `staging`
- Channel: `stable`
- S3 Path: `staging/channels/stable/appcast-*.xml`
- 用户群：预发布测试团队

## 🎮 GitHub Actions 手动触发指南

在 GitHub Actions 界面选择参数时：

### 1. 构建 main 分支的 nightly 版本

```yaml
ref: (留空或填 main)
environment: auto  # 自动检测为 production
channel: auto      # 自动检测为 nightly
```

✅ 结果：`production/nightly/`

### 2. 构建正式版本

```yaml
ref: v1.0.0
environment: auto  # 自动检测为 production
channel: auto      # 自动检测为 stable
```

✅ 结果：`production/stable/`

### 3. 测试功能分支

```yaml
ref: feature/my-feature
environment: auto  # 自动检测为 development
channel: auto      # 自动检测为 dev
```

✅ 结果：`development/dev/`

### 4. 强制指定环境和渠道（高级用户）

```yaml
ref: main
environment: production
channel: nightly
```

✅ 结果：`production/nightly/`

### ⚠️ 注意事项

- 如果手动选择 `production` + `stable`，必须使用 tag (v1.0.0)
- main/master 分支不能使用 `stable` channel
- **推荐使用 'auto' 让系统自动检测**

## 🎛️ 上线（Promote）时的环境/渠道选择

构建与上线分离后（见 [RELEASE_GUIDE.md](./RELEASE_GUIDE.md#两步式发布与灰度控制)），
上线由 **Promote OTA Release** 工作流执行，它使用与本指南**完全相同的
environment / channel 下拉选项**：

| 工作流 | 作用 | environment/channel 取值 |
|--------|------|--------------------------|
| `Release CN` / `Release Intl` | 构建 + 上传（`publish=false` 默认，不改 feed） | 按本指南的映射自动/手选 |
| `Promote OTA Release` | 上线 + 灰度（重生成 feed，写 rollout.json） | 手选，见下 |
| `OTA Status` | 只读查看灰度状态 | 手选，同上 |

**选择规则（比构建更严格——没有 auto，全部手选）**：

1. **必须与客户端烧入的组合完全一致**。客户端读的是
   `ota_config.yaml` 里 `environment → channel` 这一对
   （如 `production → stable`、`test → beta`、`development → dev`）。
   Promote 写到了别的组合（例如 `production + beta` 而客户端是
   `production + stable`），等于写进客户端永远不会读的目录——**无效果**。
2. **`app` 与客户端发行版对应**：`cn` → COS 桶（eCan.cn），`intl` → S3 桶。
3. **默认即全量**：`percent=100` 为默认值，promote 后所有人都能看到；
   灰度需要时才显式选小值（5/10/20/50），随后用 `ramp` 逐步放大。

> 这也是 kill switch 的位置：出问题时在 Promote 工作流选
> `action=pause`（同 environment/channel），秒级生效、无需重建。

## 🌍 与主流软件的对比

### Chrome/Chromium

```
stable channel   ← release tags
beta channel     ← beta branch
dev channel      ← main branch
canary channel   ← nightly builds from main
```

### VS Code

```
stable           ← release tags
insiders         ← main branch nightly builds
```

### Firefox

```
release          ← release tags
beta             ← beta branch
nightly          ← main branch daily builds
```

### eCan.ai（我们的方案）

```
production/stable   ← v1.0.0 tags
production/beta     ← v1.0.0-rc.1 tags
production/nightly  ← main/master branch
staging/stable      ← staging branch
```

## 🔄 用户更新渠道订阅

用户可以在应用设置中选择订阅不同的更新渠道：

1. **Stable（稳定版）**：
   - 订阅：`production/channels/stable/appcast-*.xml`
   - 特点：最稳定，更新频率低
   - 推荐：所有用户

2. **Beta（测试版）**：
   - 订阅：`production/channels/beta/appcast-*.xml`
   - 特点：新功能预览，可能有 bug
   - 推荐：尝鲜用户

3. **Nightly（每日构建）**：
   - 订阅：`production/channels/nightly/appcast-*.xml`
   - 特点：最新功能，每日更新
   - 推荐：开发者、高级用户

## 📂 S3 目录结构

```
ecan-releases/
├── production/
│   ├── channels/
│   │   ├── stable/          ← v1.0.0 tags ONLY
│   │   │   ├── appcast-windows-amd64.xml
│   │   │   ├── appcast-macos-amd64.xml
│   │   │   ├── appcast-macos-aarch64.xml
│   │   │   └── releases/
│   │   │       └── v1.0.0/
│   │   │           ├── windows/amd64/
│   │   │           ├── macos/amd64/
│   │   │           └── macos/aarch64/
│   │   ├── beta/            ← v1.0.0-rc.1 tags
│   │   │   └── releases/v1.0.0-rc.1/
│   │   └── nightly/         ← main/master branch
│   │       ├── appcast-windows-amd64.xml
│   │       └── releases/1.0.1-main-abc1234/
├── staging/
│   └── channels/
│       ├── stable/          ← staging branch
│       └── beta/            ← v1.0.0-beta.1 tags
├── test/
│   └── channels/
│       └── dev/             ← v1.0.0-alpha.1 tags
└── development/
    └── channels/
        └── dev/             ← develop/feature branches
```

## ✅ 优势总结

1. **清晰的分离**：
   - 稳定版本（stable）：只来自正式 tag
   - 每日构建（nightly）：来自 main 分支
   - 不会互相覆盖

2. **用户选择**：
   - 保守用户：订阅 `production/stable`
   - 尝鲜用户：订阅 `production/nightly`
   - 测试用户：订阅 `production/beta`

3. **符合行业标准**：
   - 与 Chrome、VS Code、Firefox 等主流软件一致
   - 开发者和用户都熟悉这种模式

4. **灵活性**：
   - 支持自动检测和手动指定
   - 多重保护机制防止误操作
   - 详细的错误提示和建议

## 📚 相关文档

- [GitHub Actions Release Workflow](../.github/workflows/release.yml)
- [Promote OTA Release Workflow](../.github/workflows/promote-release.yml)
- [OTA Status Workflow](../.github/workflows/ota-status.yml)
- [两步式发布与灰度控制](./RELEASE_GUIDE.md#两步式发布与灰度控制)
- [OTA Update System](./OTA_SYSTEM.md)
- [Appcast Generation](./build_system/scripts/generate_appcast.py)

---

**最后更新**: 2026-10-01
**版本**: 2.0
**状态**: ✅ 已实施
