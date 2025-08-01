# ECBot 构建系统

简洁的跨平台构建系统，支持 macOS 和 Windows 应用打包。

## 🚀 快速开始

### 本地构建
```bash
# 开发模式 (快速)
python build.py dev

# 生产模式 (优化)
python build.py prod

# 强制重建
python build.py prod --force
```

### GitHub Actions 构建
- 推送代码到 `main` 或 `develop` 分支自动触发
- 或手动触发: Actions → Build Windows EXE → Run workflow

## 📦 构建产物

### macOS
- `dist/ECBot.app` - macOS 应用程序

### Windows
- `dist/ECBot/ECBot.exe` - Windows 应用程序
- `dist/ECBot-Setup.exe` - Windows 安装包

## ⚙️ 配置

编辑 `build_config.json` 自定义构建配置：
- 应用信息 (名称、版本、图标)
- 数据文件包含
- PyInstaller 配置
- 安装包设置

## 🔧 故障排除

### 常见问题
1. **依赖缺失**: `pip install -r requirements-base.txt`
2. **构建失败**: 使用 `--force` 强制重建
3. **权限问题**: 检查目录权限

### 调试
```bash
# 查看详细日志
python build.py dev -v

# 清理缓存
python build.py --clean-cache
```

---

**💡 提示**: 生产模式会自动创建 Windows 安装包。 