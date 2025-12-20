# GitHub Actions Runner 定价和免费替代方案

## 📊 Runner 类型和定价

### macOS Runners 完整列表

| Runner Label | 架构 | 类型 | 免费额度 | 付费价格 | 需要计划 |
|-------------|------|------|---------|---------|---------|
| **Standard Runners (免费额度内)** |
| `macos-latest` | ARM64 | Standard | ✅ 包含 | 10x 倍数 | Free/Pro/Team |
| `macos-14` | ARM64 | Standard | ✅ 包含 | 10x 倍数 | Free/Pro/Team |
| `macos-15` | ARM64 | Standard | ✅ 包含 | 10x 倍数 | Free/Pro/Team |
| **Large Runners (需要付费计划)** |
| `macos-13-large` | x86_64 | Large | ❌ 无 | ~$0.16/分钟 | Team/Enterprise |
| `macos-14-large` | x86_64 | Large | ❌ 无 | ~$0.16/分钟 | Team/Enterprise |
| `macos-15-large` | x86_64 | Large | ❌ 无 | ~$0.16/分钟 | Team/Enterprise |
| `macos-latest-large` | x86_64 | Large | ❌ 无 | ~$0.16/分钟 | Team/Enterprise |
| **XLarge Runners (需要付费计划)** |
| `macos-13-xlarge` | ARM64 | XLarge | ❌ 无 | ~$0.32/分钟 | Team/Enterprise |
| `macos-14-xlarge` | ARM64 | XLarge | ❌ 无 | ~$0.32/分钟 | Team/Enterprise |
| `macos-15-xlarge` | ARM64 | XLarge | ❌ 无 | ~$0.32/分钟 | Team/Enterprise |
| `macos-latest-xlarge` | ARM64 | XLarge | ❌ 无 | ~$0.32/分钟 | Team/Enterprise |

### Windows Runners

| Runner Label | 类型 | 免费额度 | 付费价格 | 需要计划 | 说明 |
|-------------|------|---------|---------|---------|------|
| `windows-latest` | Standard | ✅ 包含 | 2x 倍数 | Free/Pro/Team | ✅ 免费（在额度内） |
| `windows-2022` | Standard | ✅ 包含 | 2x 倍数 | Free/Pro/Team | ✅ 免费（在额度内） |
| `windows-2019` | Standard | ✅ 包含 | 2x 倍数 | Free/Pro/Team | ✅ 免费（在额度内） |

**重要说明**: 
- ✅ Windows 标准 runners (`windows-latest`, `windows-2022`, `windows-2019`) **包含在免费额度内**
- ⚠️ 使用 **2x 分钟倍数**（1 实际分钟 = 2 计费分钟）
- 💰 超出免费额度后按 **$0.016/分钟** 计费

### Linux Runners

| Runner Label | 类型 | 免费额度 | 付费价格 | 需要计划 |
|-------------|------|---------|---------|---------|
| `ubuntu-latest` | Standard | ✅ 包含 | 1x 倍数 | Free/Pro/Team |
| `ubuntu-22.04` | Standard | ✅ 包含 | 1x 倍数 | Free/Pro/Team |
| `ubuntu-20.04` | Standard | ✅ 包含 | 1x 倍数 | Free/Pro/Team |

## 💰 定价详情

### 免费额度（每月）

| GitHub 计划 | 免费分钟数 | 存储空间 |
|------------|-----------|---------|
| **Free** | 2,000 分钟 | 500 MB |
| **Pro** | 3,000 分钟 | 1 GB |
| **Team** | 3,000 分钟 | 2 GB |
| **Enterprise** | 50,000 分钟 | 50 GB |

### 分钟倍数（Minute Multipliers）

| 操作系统 | 倍数 | 实际消耗 | 示例 |
|---------|------|---------|------|
| **Linux** | 1x | 1 分钟 = 1 分钟 | 2000 免费分钟 = 2000 实际分钟 |
| **Windows** | 2x | 1 分钟 = 2 分钟 | 2000 免费分钟 = 1000 实际分钟 |
| **macOS** | 10x | 1 分钟 = 10 分钟 | 2000 免费分钟 = 200 实际分钟 |

### 超出免费额度后的价格

| 操作系统 | 每分钟价格 | 每小时价格 |
|---------|-----------|-----------|
| **Linux** | $0.008 | $0.48 |
| **Windows** | $0.016 | $0.96 |
| **macOS** | $0.080 | $4.80 |

### Large/XLarge Runners 价格

| Runner 类型 | 估算价格/分钟 | 估算价格/小时 | 说明 |
|------------|--------------|--------------|------|
| **macOS Large** | ~$0.16 | ~$9.60 | Intel x86_64, 需要 Team+ |
| **macOS XLarge** | ~$0.32 | ~$19.20 | ARM64 高性能, 需要 Team+ |

**注意**: Large/XLarge runners 的具体价格需要联系 GitHub 销售团队确认。

## 🚨 当前配置分析

### 我们的配置

```yaml
strategy:
  matrix:
    include:
      - arch: amd64
        runner: macos-14-large  # ❌ 付费 runner
      - arch: aarch64
        runner: macos-latest    # ✅ 免费 runner (在额度内)
```

### 成本估算

假设每次构建：
- macOS amd64: 30 分钟
- macOS aarch64: 30 分钟
- 每月构建 20 次

**当前配置成本**:
```
macOS amd64 (macos-14-large):
  30 分钟 × 20 次 × $0.16/分钟 = $96/月

macOS aarch64 (macos-latest):
  30 分钟 × 20 次 = 600 实际分钟
  600 × 10 (倍数) = 6000 计费分钟
  
  如果使用 Free 计划 (2000 免费分钟):
    超出: 6000 - 2000 = 4000 分钟
    成本: 4000 × $0.008 = $32/月
  
  如果使用 Team 计划 (3000 免费分钟):
    超出: 6000 - 3000 = 3000 分钟
    成本: 3000 × $0.008 = $24/月

总成本: $96 + $24-32 = $120-128/月
```

## ✅ 免费替代方案

### 方案 1: 只使用 ARM64 (推荐) 🌟

**配置**:
```yaml
strategy:
  matrix:
    include:
      - arch: aarch64
        runner: macos-latest  # ✅ 免费 (在额度内)
        target_arch: arm64
        pyinstaller_arch: arm64
```

**优点**:
- ✅ 完全免费（在免费额度内）
- ✅ 性能更好（Apple Silicon）
- ✅ 未来兼容（Intel 将在 2027 弃用）
- ✅ 支持大多数现代 Mac 用户

**缺点**:
- ❌ 不支持 Intel Mac 用户（2020年前购买）

**适用场景**:
- 用户群主要使用 Apple Silicon Mac
- 预算有限
- 可以接受不支持旧 Intel Mac

### 方案 2: 使用 Self-Hosted Runner (完全免费) 🌟🌟

**配置**:
```yaml
strategy:
  matrix:
    include:
      - arch: amd64
        runner: [self-hosted, macOS, X64]  # ✅ 完全免费
      - arch: aarch64
        runner: [self-hosted, macOS, ARM64]  # ✅ 完全免费
```

**优点**:
- ✅ 完全免费（无使用限制）
- ✅ 支持所有架构
- ✅ 完全控制硬件
- ✅ 可以使用更强大的机器

**缺点**:
- ❌ 需要自己维护硬件
- ❌ 需要配置和管理 runner
- ❌ 需要处理安全问题
- ❌ 需要稳定的网络连接

**成本**:
- 硬件成本（一次性或租用）
- 电费和网络费用
- 维护时间成本

**适用场景**:
- 有可用的 Mac 硬件
- 构建频繁，长期使用
- 需要特殊配置或软件

### 方案 3: 混合方案（推荐用于过渡期）

**配置**:
```yaml
strategy:
  matrix:
    include:
      - arch: amd64
        runner: [self-hosted, macOS, X64]  # ✅ 自建 Intel Mac
      - arch: aarch64
        runner: macos-latest  # ✅ GitHub 免费 ARM runner
```

**优点**:
- ✅ 支持所有架构
- ✅ ARM 构建免费
- ✅ Intel 构建在自己硬件上

**缺点**:
- ⚠️ 需要维护一台 Intel Mac

### 方案 4: 使用 macOS-13 (临时方案，不推荐)

**配置**:
```yaml
# ❌ 不推荐：macOS-13 将在 2024-12-04 移除
strategy:
  matrix:
    include:
      - arch: amd64
        runner: macos-13  # ⚠️ 即将移除
```

**状态**: ❌ **已弃用，2024-12-04 后不可用**

## 📊 方案对比

| 方案 | Intel 支持 | ARM 支持 | 月成本 | 维护成本 | 推荐度 |
|------|-----------|---------|--------|---------|--------|
| **只用 ARM** | ❌ | ✅ | $0-32 | 低 | ⭐⭐⭐⭐⭐ |
| **Self-Hosted** | ✅ | ✅ | $0 | 高 | ⭐⭐⭐⭐ |
| **混合方案** | ✅ | ✅ | $0-32 | 中 | ⭐⭐⭐⭐ |
| **Large Runners** | ✅ | ✅ | $120+ | 低 | ⭐⭐ |

## 🎯 推荐方案

### 短期（立即实施）

**推荐: 方案 1 - 只使用 ARM64**

```yaml
# 修改 release.yml
strategy:
  matrix:
    include:
      - arch: aarch64
        runner: macos-latest
        target_arch: arm64
        pyinstaller_arch: arm64
```

**理由**:
1. ✅ 立即可用，无需额外配置
2. ✅ 完全免费（在免费额度内）
3. ✅ 性能更好
4. ✅ 未来兼容

**用户影响评估**:
- 统计 Intel Mac 用户比例
- 如果 < 10%，可以接受停止支持
- 提供最后的 Intel 版本下载
- 提前 3-6 个月通知用户

### 中期（1-3个月）

**如果必须支持 Intel: 方案 2 或 3 - Self-Hosted Runner**

**步骤**:
1. 购买或租用一台 Intel Mac Mini
2. 配置 Self-Hosted Runner
3. 更新 workflow 配置
4. 测试验证

**成本**:
- Mac Mini (2020 Intel): ~$500-800 (二手)
- 或租用云 Mac: ~$50-100/月

### 长期（2025+）

**目标: 完全迁移到 ARM64**

**时间表**:
- 2024 Q4: 评估用户基础
- 2025 Q1: 通知用户停止 Intel 支持
- 2025 Q2: 提供最后的 Intel 版本
- 2025 Q3: 完全停止 Intel 构建

## 🔧 实施步骤

### 立即修改为只支持 ARM64

```yaml
# 1. 修改 release.yml
build-macos:
  name: Build macOS ARM64
  needs: validate-tag
  if: |
    needs.validate-tag.outputs.tag-valid == 'true' &&
    (github.event.inputs.platform == 'macos' || github.event.inputs.platform == 'all')
  runs-on: macos-latest  # ARM64 runner
  env:
    BUILD_ARCH: aarch64
    TARGET_ARCH: arm64
    PYINSTALLER_TARGET_ARCH: arm64
  steps:
    # ... 构建步骤
```

```yaml
# 2. 更新 artifact 名称
- name: Upload macOS artifacts
  with:
    name: eCan-macos-aarch64-${{ needs.validate-tag.outputs.version }}-s3-transfer
```

```yaml
# 3. 更新 upload-to-s3 下载步骤
- name: Download macOS artifacts
  if: needs.build-macos.result == 'success'
  with:
    name: eCan-macos-aarch64-${{ needs.validate-tag.outputs.version }}-s3-transfer
```

### 配置 Self-Hosted Runner（如果需要）

**步骤**:

1. **在 Mac 上安装 Runner**
   ```bash
   # 下载 runner
   mkdir actions-runner && cd actions-runner
   curl -o actions-runner-osx-x64-2.311.0.tar.gz -L \
     https://github.com/actions/runner/releases/download/v2.311.0/actions-runner-osx-x64-2.311.0.tar.gz
   tar xzf ./actions-runner-osx-x64-2.311.0.tar.gz
   
   # 配置 runner
   ./config.sh --url https://github.com/YOUR-ORG/YOUR-REPO \
     --token YOUR-TOKEN \
     --labels self-hosted,macOS,X64
   
   # 启动 runner
   ./run.sh
   ```

2. **配置为服务（可选）**
   ```bash
   sudo ./svc.sh install
   sudo ./svc.sh start
   ```

3. **更新 workflow**
   ```yaml
   runs-on: [self-hosted, macOS, X64]
   ```

## 📈 成本节省计算

### 当前配置 vs 推荐配置

| 项目 | 当前 (Large Runner) | 推荐 (ARM Only) | 节省 |
|------|-------------------|----------------|------|
| **月构建次数** | 20 | 20 | - |
| **Intel 构建** | $96 | $0 | $96 |
| **ARM 构建** | $24-32 | $0-32 | $0-24 |
| **总成本** | $120-128 | $0-32 | $88-128 |
| **年成本** | $1,440-1,536 | $0-384 | $1,056-1,536 |

**结论**: 切换到只支持 ARM64 可以节省 **$1,000-1,500/年**

## 📚 参考资料

- [GitHub Actions Pricing](https://docs.github.com/en/billing/managing-billing-for-github-actions/about-billing-for-github-actions)
- [About GitHub-hosted runners](https://docs.github.com/en/actions/using-github-hosted-runners/about-github-hosted-runners)
- [Using larger runners](https://docs.github.com/en/actions/using-github-hosted-runners/using-larger-runners)
- [Self-hosted runners](https://docs.github.com/en/actions/hosting-your-own-runners)

---

**建议**: 立即切换到只支持 ARM64，节省成本并提升性能。
