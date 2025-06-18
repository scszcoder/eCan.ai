# Monaco Editor 本地加载配置

本项目已配置为使用本地加载的 Monaco Editor，而不是 CDN。

## 配置说明

### 1. 文件结构
```
public/
  monaco-editor/
    vs/                    # Monaco Editor 的核心文件
      loader.js           # 加载器
      editor/             # 编辑器核心
      language/           # 语言支持
      basic-languages/    # 基础语言
      base/               # 基础组件
      nls.messages.*.js   # 国际化文件
```

### 2. 代码配置

在 `src/modules/skill-editor/components/code-editor/CodeEditor.tsx` 中：

```typescript
// 配置Monaco Editor使用本地路径
loader.config({
  paths: {
    vs: '/monaco-editor/vs'
  }
});
```

### 3. Vite 配置

在 `vite.config.ts` 中已配置：
- 优化依赖包含 Monaco Editor 的 worker 文件
- 构建时 Monaco Editor 会被单独打包

### 4. 构建脚本

在 `scripts/build.js` 中已添加自动复制 Monaco Editor 文件的逻辑。

## 使用方法

### 开发环境
```bash
npm run dev
```

### 生产构建
```bash
npm run build
```

构建脚本会自动复制 Monaco Editor 文件到 public 目录。

### 手动复制文件
```bash
npm run copy-monaco
```

## 优势

1. **离线可用**: 不依赖外部 CDN，可以在离线环境中使用
2. **性能更好**: 本地文件加载速度更快
3. **版本控制**: 可以精确控制 Monaco Editor 的版本
4. **安全性**: 避免 CDN 可能的安全风险

## 注意事项

1. 确保 `node_modules/monaco-editor/min/vs` 目录存在
2. 构建前会自动复制文件，无需手动操作
3. 如果更新 Monaco Editor 版本，需要重新运行构建脚本 