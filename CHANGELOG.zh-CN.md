# 更新日志

本文件记录 eCan.ai 的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [未发布]

## [1.0.1] - 2025-11-21

### 新增
- S3 加速下载地址支持 - 为每个更新包提供标准和加速两个下载 URL，提升全球下载速度
- OTA 自动检查延迟配置 - 开发环境 5 秒快速检查，生产环境 2 分钟延迟，避免影响启动体验
- 开发环境独立 OTA 开关 - 新增 `dev_ota_check_enabled` 配置项，可单独控制开发环境的 OTA 检查
- pip 依赖缓存优化 - GitHub Actions 使用 `requirements.txt` 和缓存机制，加速构建流程

### 修复
- 修复重启脚本命令解析问题 - Unix shell 脚本现在能正确处理带参数的命令
- 修复 Windows 构建流程缺少 `.sig` 签名文件的问题 - 确保所有平台的签名文件都正确上传
- 修复模拟构建缺少签名文件的问题 - 测试环境现在也会生成模拟签名文件

### 变更
- 优化 GitHub Actions checkout 性能 - 构建 jobs 使用浅克隆（fetch-depth: 1）节省约 28% 时间
- 统一管理 Python 依赖 - 使用 `build_system/scripts/requirements.txt` 集中管理依赖版本
- 改进日志输出 - OTA 延迟检查现在会显示当前环境信息，便于调试

### 性能优化
- 构建时间优化 - 每次构建节省约 21 秒（约 28% 提升）
- 依赖安装优化 - pip 缓存命中时节省约 80% 的安装时间
- 带宽优化 - 每次构建节省约 30-100 MB 的网络传输

## [1.0.0] - 2025-11-20

### 新增
- 🎉 初始版本发布
- OTA 自动更新功能
  - 支持 macOS 和 Windows 平台
  - 自动检测新版本
  - 后台下载更新包
  - 静默安装（可选）
  - 自动重启应用（可选）
- Ed25519 数字签名验证
  - 确保更新包的完整性和真实性
  - 防止中间人攻击
- Sparkle 兼容的 Appcast 格式
  - 标准化的更新信息格式
  - 支持版本比较和平台筛选
- S3 存储和分发
  - 可靠的云存储
  - 全球 CDN 加速
- 多环境支持
  - development（开发环境）
  - test（测试环境）
  - staging（预发布环境）
  - production（生产环境）
- GitHub Actions 自动化构建和发布流程
  - 自动构建多平台安装包
  - 自动签名和验证
  - 自动上传到 S3
  - 自动生成 Appcast

### 安全
- Ed25519 数字签名验证 - 确保更新包未被篡改
- 安全的更新下载和安装流程 - 使用 HTTPS 传输，验证签名后才安装

---

## 版本说明

### 版本号格式
- 主版本号.次版本号.修订号（例如：1.0.0）
- 遵循语义化版本规范

### 更新类型说明
- **新增（Added）**：新增功能
- **变更（Changed）**：功能变更
- **弃用（Deprecated）**：即将废弃的功能
- **移除（Removed）**：已移除的功能
- **修复（Fixed）**：问题修复
- **安全（Security）**：安全相关更新
- **性能优化（Performance）**：性能改进

### 支持的语言
- 英文（English）：CHANGELOG.md
- 简体中文（Simplified Chinese）：CHANGELOG.zh-CN.md

[未发布]: https://github.com/scszcoder/eCan.ai/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/scszcoder/eCan.ai/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/scszcoder/eCan.ai/releases/tag/v1.0.0
