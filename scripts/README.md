# ECBot 开发工具

这个目录包含了 ECBot 项目的各种开发、构建和测试脚本。

## 使用方法

### 1. 开发环境

启动开发环境（包括前端和后端服务）：

```bash
# 在浏览器中运行（支持热重载和开发者工具）
python scripts/main.py dev

# 在桌面应用中运行（更接近生产环境）
python scripts/main.py dev --desktop
```

开发环境特点：
- 前端服务运行在 http://localhost:5173
- 后端服务运行在 ws://localhost:6000
- 支持热重载，修改代码后自动更新
- 支持两种运行模式：
  - 浏览器模式：方便调试和开发
  - 桌面应用模式：更接近生产环境

浏览器模式优势：
- 可以使用浏览器开发者工具
- 支持热重载和实时预览
- 方便调试和测试
- 按 Ctrl+C 可以优雅地关闭所有服务

桌面应用模式优势：
- 更接近生产环境
- 可以测试桌面应用集成
- 支持窗口大小调整
- 关闭窗口时自动清理所有服务

### 2. 生产环境

构建并启动生产环境：

```bash
# 1. 首先构建项目
python scripts/main.py build

# 2. 启动桌面应用
python scripts/start.py
```

生产环境特点：
- 前端页面嵌入到桌面应用中
- 后端 WebSocket 服务运行在端口 6000
- 支持 SPA 路由
- 自动处理 CORS 和静态文件服务
- 关闭窗口时自动清理所有服务

桌面应用功能：
- 使用 PySide6 创建原生窗口
- 内置 WebView 显示前端页面
- 窗口大小可调整（最小 1200x800）
- 支持所有现代 Web 功能

生产环境目录结构：
```
dist/
├── frontend/          # 前端静态文件
│   ├── index.html
│   ├── assets/
│   └── ...
└── backend/          # 后端文件
    ├── main.py
    ├── services/
    └── ...
```

### 3. 构建项目

构建整个项目：

```bash
# 构建整个项目（前端和后端）
python scripts/main.py build

# 仅构建前端
python scripts/main.py build --frontend-only

# 仅构建后端
python scripts/main.py build --backend-only
```

构建完成后：
- 前端构建文件位于 `gui_v2/dist`
- 后端文件位于 `backend`
- 完整的发布文件位于 `dist` 目录

### 4. 运行测试

运行所有测试：

```bash
# 运行所有测试（前端和后端）
python scripts/main.py test

# 仅运行前端测试
python scripts/main.py test --frontend-only

# 仅运行后端测试
python scripts/main.py test --backend-only
```

测试结果：
- 前端测试结果会显示在控制台
- 后端测试会显示详细的测试报告
- 如果测试失败，会显示具体的失败原因

### 5. 清理构建文件

清理所有构建文件：

```bash
# 清理所有构建文件
python scripts/main.py clean

# 仅清理前端文件
python scripts/main.py clean --frontend-only

# 仅清理后端文件
python scripts/main.py clean --backend-only

# 仅清理发布目录
python scripts/main.py clean --dist-only
```

清理范围：
- 前端：node_modules、dist、.cache 等
- 后端：__pycache__、.pyc、临时文件等
- 发布目录：dist 目录下的所有文件

## 可用命令

所有命令都可以通过 `python scripts/main.py <command>` 来执行。

### 开发环境

启动开发环境（包括前端和后端服务）：

```bash
python scripts/main.py dev
```

选项：
- `--desktop`: 在桌面应用中运行（而不是浏览器）

### 构建项目

构建整个项目：

```bash
python scripts/main.py build
```

选项：
- `--frontend-only`: 仅构建前端
- `--backend-only`: 仅构建后端

### 运行测试

运行所有测试：

```bash
python scripts/main.py test
```

选项：
- `--frontend-only`: 仅运行前端测试
- `--backend-only`: 仅运行后端测试

### 清理构建文件

清理所有构建文件：

```bash
python scripts/main.py clean
```

选项：
- `--frontend-only`: 仅清理前端文件
- `--backend-only`: 仅清理后端文件
- `--dist-only`: 仅清理发布目录

## 脚本说明

### dev.py

开发环境管理脚本，负责：
- 启动前端开发服务器
- 启动后端服务器
- 支持浏览器和桌面应用两种模式
- 进程管理和清理

### start.py

生产环境启动脚本，负责：
- 启动后端服务
- 启动前端静态文件服务器
- 创建桌面应用窗口
- 嵌入前端页面
- 进程管理和清理

### build.py

项目构建脚本，负责：
- 安装前端依赖
- 构建前端项目
- 安装后端依赖
- 准备发布目录

### test.py

测试运行脚本，负责：
- 运行前端测试
- 运行后端测试
- 测试结果报告

### clean.py

清理脚本，负责：
- 清理前端构建文件
- 清理后端构建文件
- 清理发布目录
- 清理临时文件和缓存

## 开发流程

1. 启动开发环境：
   ```bash
   # 浏览器模式（开发调试）
   python scripts/main.py dev

   # 桌面应用模式（测试集成）
   python scripts/main.py dev --desktop
   ```

2. 运行测试：
   ```bash
   python scripts/main.py test
   ```

3. 构建项目：
   ```bash
   python scripts/main.py build
   ```

4. 启动生产环境：
   ```bash
   python scripts/start.py
   ```

5. 清理构建文件：
   ```bash
   python scripts/main.py clean
   ```

## 注意事项

1. 确保已安装所有必要的依赖：
   - Python 3.8+
   - Node.js 16+
   - npm 8+
   - PySide6
   - Qt WebEngine

2. 在运行构建命令前，建议先运行清理命令：
   ```bash
   python scripts/main.py clean
   python scripts/main.py build
   ```

3. 如果遇到问题，可以尝试：
   - 清理所有构建文件
   - 重新安装依赖
   - 检查日志输出

4. 开发环境注意事项：
   - 确保端口 5173 和 6000 未被占用
   - 如果服务启动失败，检查依赖是否正确安装
   - 浏览器模式：使用 Ctrl+C 关闭服务
   - 桌面应用模式：关闭窗口自动清理服务

5. 生产环境注意事项：
   - 确保端口 8080 和 6000 未被占用
   - 确保已运行构建命令生成发布文件
   - 检查 dist 目录结构是否正确
   - 关闭窗口时自动清理所有服务

6. 构建注意事项：
   - 构建前确保所有依赖都已正确安装
   - 构建失败时检查错误日志
   - 发布前进行完整测试

7. 测试注意事项：
   - 运行测试前确保开发环境已关闭
   - 测试失败时查看详细的错误信息
   - 定期运行测试以确保代码质量 