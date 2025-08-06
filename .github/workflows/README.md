# GitHub Actions Workflows

本项目包含一个主要的 GitHub Actions workflow，用于自动化构建和发布流程。

## Workflows 概览

### Release Build (`release.yml`)
**统一发布流程** - 当创建 tag 或 release 时触发

**触发条件：**
- 推送 tag：`v*` (如 `v1.0.0`, `v2.1.3`)
- 创建/编辑/发布 GitHub Release
- 手动触发（支持平台选择）

**功能：**
- ✅ 验证 tag 格式
- ✅ 支持选择性构建（Windows、macOS 或全部）
- ✅ 并行构建 Windows 和 macOS 版本
- ✅ 自动创建 GitHub Release
- ✅ 上传构建产物
- ✅ 统一管理多平台构建

## 使用方法

### 创建新版本发布

1. **准备代码**
   ```bash
   git checkout main
   git pull origin main
   ```

2. **创建并推送 tag**
   ```bash
   # 创建 tag (遵循语义化版本控制)
   git tag v1.0.0
   
   # 推送 tag 到远程仓库
   git push origin v1.0.0
   ```

3. **自动触发构建**
   - 推送 tag 后，GitHub Actions 会自动触发构建流程
   - 构建完成后会自动创建 GitHub Release

### Tag 命名规范

遵循 [语义化版本控制 (SemVer)](https://semver.org/lang/zh-CN/) 规范：

- **正式版本**：`v1.0.0`, `v2.1.3`
- **预发布版本**：`v1.0.0-alpha.1`, `v2.1.3-beta.2`
- **构建版本**：`v1.0.0+build.1`

### 平台选择功能

#### 自动触发（Tag/Release）
- 推送 tag 时：自动构建所有平台
- 创建 Release 时：自动构建所有平台

#### 手动触发
支持选择特定平台进行构建：

- **all** (默认)：构建 Windows 和 macOS 版本
- **windows**：仅构建 Windows 版本
- **macos**：仅构建 macOS 版本

#### 使用场景
- **快速测试**：选择单个平台进行快速构建测试
- **平台特定修复**：只构建需要修复的平台
- **节省资源**：避免不必要的平台构建
- **紧急发布**：快速构建特定平台版本

### 手动触发

1. 在 GitHub 仓库页面，点击 "Actions" 标签
2. 选择 "Release Build" workflow
3. 点击 "Run workflow" 按钮
4. 选择构建平台：
   - **all**: 构建所有平台（默认）
   - **windows**: 仅构建 Windows 版本
   - **macos**: 仅构建 macOS 版本
5. 选择分支并点击 "Run workflow"

## 构建产物

### Windows
- `ECBot-Setup.exe` - 安装程序
- `ECBot/ECBot.exe` - 便携版可执行文件

### macOS
- `ECBot.pkg` - macOS 安装包
- `ECBot.app` - macOS 应用程序包（便携版）

## 版本管理

### 版本信息传递
- 自动从 Git 标签提取版本号
- 版本信息自动应用到构建产物
- 支持语义化版本号 (SemVer)
- 构建产物文件名包含版本号

### 版本应用范围
- **Windows 安装包**：`ECBot-Setup.exe` 中的应用信息
- **macOS 安装包**：`ECBot-{version}.pkg` 文件名和包信息
- **应用程序**：可执行文件中的应用版本信息
- **Release 说明**：自动生成包含版本信息的发布说明

## 环境要求

### Windows 构建
- Python 3.11
- Node.js 18
- Inno Setup 6.2.2
- PyInstaller
- pywin32-ctypes

### macOS 构建
- Python 3.11
- Node.js 18
- PyInstaller

## 故障排除

### 常见问题

1. **构建失败**
   - 检查依赖项是否正确安装
   - 查看构建日志获取详细错误信息
   - 确保代码没有语法错误

2. **Release 创建失败**
   - 确保 tag 格式正确
   - 检查 GitHub Token 权限
   - 验证构建产物是否存在

3. **端口冲突**
   - 构建过程中可能遇到端口占用问题
   - 系统会自动处理端口冲突

### 日志查看

1. 在 GitHub Actions 页面查看构建日志
2. 下载构建产物查看详细日志文件
3. 检查 `build.log` 文件获取构建过程信息

## 配置说明

### 缓存配置
- Python 依赖缓存：基于 `requirements*.txt` 文件哈希
- Node.js 依赖缓存：基于 `package-lock.json`

### 超时设置
- 构建超时：45 分钟
- 下载超时：10 分钟

### 产物保留
- 构建产物保留：30 天
- Release 文件：永久保留

## 安全说明

- 使用 `GITHUB_TOKEN` 进行身份验证
- 构建产物经过验证确保完整性
- 支持预发布版本标记

## 更新日志

- **v1.0.0**: 初始版本，支持基本的 tag 触发构建
- **v1.1.0**: 添加 Release 自动创建功能
- **v1.2.0**: 优化构建流程，添加并行构建支持 