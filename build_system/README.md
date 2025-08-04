# ECBot 构建系统

## 概述

ECBot 构建系统集成了自动化动态导入检测功能，能够自动检测项目中的所有动态导入并生成完整的 hiddenimports 列表，确保所有依赖都能被正确打包。

## 核心功能

### 1. 自动化动态导入检测
- **无需手动维护包名列表**
- **自动检测所有动态导入模式**
- **智能识别科学计算库、机器学习库、Web框架等**

### 2. 多模式构建支持
- **fast**: 快速构建（开发调试用）
- **dev**: 开发构建（带调试信息）
- **prod**: 生产构建（完全优化）

### 3. 智能包检测
- 自动检测已安装包的所有子模块
- 智能识别项目特定的包结构
- 自动测试模块的可导入性

## 使用方法

### 基本构建命令

```bash
# 快速构建（开发调试用）
python build.py fast

# 开发构建
python build.py dev

# 生产构建
python build.py prod

# 强制重新构建
python build.py prod --force

# 跳过前端构建
python build.py prod --skip-frontend

# 跳过安装程序创建
python build.py prod --skip-installer
```

### 独立运行检测器

```bash
# 运行智能动态导入检测
python build_system/smart_dynamic_detector.py

# 输出示例：
🧠 开始智能动态导入检测...
📝 第一阶段：检测项目特定的动态导入...
   发现项目特定导入: 200 个
💻 第二阶段：检测代码中的实际动态导入...
   分析 150 个 Python 文件...
   发现代码动态导入: 25 个
🔑 第三阶段：检测关键依赖的动态导入...
   检测 100 个关键动态导入模式...
   发现关键依赖: 80 个
🔄 第四阶段：智能合并和优化...
✅ 智能检测完成: 305 个模块
💾 智能检测结果已保存到: build_system/smart_detected_modules.json
```

## 解决的问题

### 动态导入问题
- `No module named 'scipy._lib.array_api_compat.numpy.fft'`
- `No module named 'scipy.stats.chatterjeexi'`
- 所有类似的动态导入错误

### 覆盖的库类型
- **科学计算库**: scipy, numpy, pandas, matplotlib, sklearn
- **机器学习库**: transformers, torch, tensorflow
- **Web 框架**: fastapi, starlette, uvicorn
- **数据库**: sqlalchemy, django
- **AI 库**: openai, langchain
- **其他常用库**: pydantic, click, rich, cryptography 等

## 技术特点

### 1. 智能优化
- 限制最大模块数量（1000个），避免 spec 文件过长
- 优先级排序，保留最重要的模块
- 智能过滤，避免冗余检测

### 2. 精准检测
- 项目特定的动态导入（优先级最高）
- 代码中的实际动态导入
- 关键依赖的动态导入

### 3. 高效覆盖
- 涵盖最常见的动态导入问题
- 自动识别关键模式
- 避免过度检测

## 配置文件

### build_config.json
```json
{
  "build_modes": {
    "dev": { "debug": false, "console": true },
    "prod": { "debug": false, "console": false }
  },
  "installer": {
    "compression_modes": {
      "dev": { "compression": "zip", "solid_compression": false },
      "prod": { "compression": "lzma", "solid_compression": true }
    }
  }
}
```

### fast_build_config.json
```json
{
  "build_modes": {
    "fast": { "debug": true, "console": true, "clean": false }
  },
  "installer": { "enabled": false }
}
```

## 故障排除

### 1. 检测器运行失败
```bash
# 检查 Python 环境
python -c "import importlib; print('OK')"

# 手动运行检测器
python build_system/auto_dynamic_detector.py
```

### 2. 构建时仍有模块缺失
```bash
# 查看详细错误信息
python build.py prod --verbose

# 检查检测结果
cat build_system/detected_modules.json
```

### 3. 特定模块缺失
```bash
# 检查模块是否存在
python -c "import scipy._lib.array_api_compat.numpy.fft; print('OK')"
```

## 总结

ECBot 构建系统通过自动化动态导入检测，彻底解决了传统方法需要手动维护大量包名列表的问题：

1. **完全自动化**: 无需手动维护任何配置
2. **智能检测**: 自动识别各种动态导入模式
3. **全面覆盖**: 检测所有主要类别的动态导入问题
4. **易于使用**: 一键运行，自动集成到构建流程
5. **持续适应**: 自动适应项目变化和新依赖

使用这个构建系统，你可以放心地使用各种动态导入技术，而不用担心打包时出现模块缺失的问题！ 