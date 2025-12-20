# GitHub Actions Composite Actions

这个目录包含了可重用的复合Action，用于消除工作流中的重复代码。

## 可用的复合Action

### 1. setup-python-env

设置Python环境，包括虚拟环境创建和依赖安装。

**输入参数:**
- `python-version`: Python版本 (默认: '3.11')
- `requirements-file`: 需求文件路径 (默认: 'requirements-base.txt')
- `platform`: 平台 (必需: 'windows', 'macos', 'linux')
- `install-pyinstaller`: 是否安装PyInstaller (默认: 'true')
- `pyinstaller-version`: PyInstaller版本 (默认: '6.15.0')
- `extra-packages`: 额外包列表，逗号分隔 (默认: '')

**使用示例:**
```yaml
- name: Setup Python Environment
  uses: ./.github/actions/setup-python-env
  with:
    platform: windows
    requirements-file: requirements-windows.txt
    extra-packages: pywin32-ctypes
```

### 2. setup-node-env

设置Node.js环境并安装前端依赖。

**输入参数:**
- `node-version`: Node.js版本 (默认: '18')
- `frontend-dir`: 前端目录路径 (默认: 'gui_v2')
- `install-command`: 安装命令 (默认: 'npm install --legacy-peer-deps')

**使用示例:**
```yaml
- name: Setup Node.js Environment
  uses: ./.github/actions/setup-node-env
  with:
    platform: windows
```

### 3. setup-ota-deps

安装和验证OTA更新依赖。

**输入参数:**
- `platform`: 平台 (必需: 'windows', 'macos')
- `verify-only`: 仅验证依赖，跳过安装 (默认: 'false')

**使用示例:**
```yaml
- name: Setup OTA Dependencies
  uses: ./.github/actions/setup-ota-deps
  with:
    platform: windows
```

### 4. check-build-env

检查构建环境并显示系统信息。

**输入参数:**
- `platform`: 平台 (必需: 'windows', 'macos')
- `matrix-arch`: 矩阵架构 (macOS用，可选)
- `matrix-target-arch`: 矩阵目标架构 (macOS用，可选)
- `matrix-pyinstaller-arch`: 矩阵PyInstaller架构 (macOS用，可选)

**使用示例:**
```yaml
- name: Check Build Environment
  uses: ./.github/actions/check-build-env
  with:
    platform: macos
    matrix-arch: ${{ matrix.arch }}
    matrix-target-arch: ${{ matrix.target_arch }}
    matrix-pyinstaller-arch: ${{ matrix.pyinstaller_arch }}
```

### 5. setup-build-dirs

创建构建和dist目录。

**输入参数:**
- `platform`: 平台 (必需: 'windows', 'macos')

**使用示例:**
```yaml
- name: Setup Build Directories
  uses: ./.github/actions/setup-build-dirs
  with:
    platform: windows
```

### 6. setup-signtool-env

安装和配置Windows SDK signtool用于代码签名。

**输入参数:**
- `skip-if-available`: 如果signtool已可用则跳过安装 (默认: 'true')
- `sdk-version`: Windows SDK版本 (默认: '2004')
- `timeout`: 安装超时时间(秒) (默认: '600')

**输出参数:**
- `signtool-available`: signtool是否可用 ('true'/'false')
- `signtool-path`: signtool.exe的路径
- `installation-method`: 安装方式 ('existing', 'found-existing', 'chocolatey', 'failed')

**使用示例:**
```yaml
- name: Setup Windows signtool Environment
  uses: ./.github/actions/setup-signtool-env
  with:
    skip-if-available: true
    sdk-version: '2004'
    timeout: '600'
```

## 优势

### 代码去重
- 消除了Windows和macOS构建步骤中的重复代码
- 统一了环境设置和依赖安装逻辑
- 减少了维护工作量

### 一致性
- 确保不同平台的构建步骤使用相同的逻辑
- 统一的错误处理和日志输出
- 标准化的环境配置

### 可维护性
- 修改逻辑只需要在一个地方进行
- 更容易测试和调试
- 清晰的参数化配置

## 使用建议

1. **新工作流**: 优先使用这些复合Action而不是重复代码
2. **现有工作流**: 逐步迁移到使用复合Action
3. **参数化**: 充分利用输入参数来适应不同需求
4. **测试**: 在本地或测试分支中验证复合Action的行为

## 扩展

如需添加新的复合Action:

1. 在 `.github/actions/` 目录下创建新的子目录
2. 创建 `action.yml` 文件定义Action
3. 在README中添加使用说明
4. 更新相关的工作流文件

## 注意事项

- 复合Action只能在GitHub Actions中使用
- 确保所有依赖的工具和脚本都可用
- 注意跨平台的兼容性
- 保持向后兼容性
