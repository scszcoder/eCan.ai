import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react({
      babel: {
        plugins: [
          ['@babel/plugin-proposal-decorators', { legacy: true }],
          ['@babel/plugin-proposal-class-properties', { loose: true }]
        ]
      }
    })
  ],
  base: './',  // 使用相对路径，支持 file:// 协议
  server: {
    port: 5173,
    strictPort: true, // 如果端口被占用，则直接退出
    host: true, // 监听所有地址
    fs: {
      // 允许访问项目根目录之外的文件
      strict: false
    },
    headers: {
      'Access-Control-Allow-Origin': '*'
    }
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    emptyOutDir: true,
    sourcemap: true,
    // 确保资源文件名包含哈希值，并禁用代码分割
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]',
        manualChunks: {
          vendor: ['react', 'react-dom'],
          monaco: [
            // 核心编辑器
            'monaco-editor/esm/vs/editor/editor.api',
            'monaco-editor/esm/vs/editor/editor.worker',
            // 语言支持
            'monaco-editor/esm/vs/language/typescript/ts.worker',
            'monaco-editor/esm/vs/language/json/json.worker',
            'monaco-editor/esm/vs/language/css/css.worker',
            'monaco-editor/esm/vs/language/html/html.worker',
            'monaco-editor/esm/vs/basic-languages/python/python.worker',
            // 基础语言支持
            'monaco-editor/esm/vs/basic-languages/javascript/javascript.worker',
            'monaco-editor/esm/vs/basic-languages/typescript/typescript.worker',
            // 语言特性
            'monaco-editor/esm/vs/language/typescript/tsMode',
            'monaco-editor/esm/vs/language/json/jsonMode',
            'monaco-editor/esm/vs/language/css/cssMode',
            'monaco-editor/esm/vs/language/html/htmlMode',
            // 编辑器功能
            'monaco-editor/esm/vs/editor/standalone/browser/accessibilityHelp/accessibilityHelp',
            'monaco-editor/esm/vs/editor/standalone/browser/inspectTokens/inspectTokens',
            'monaco-editor/esm/vs/editor/standalone/browser/iPadShowKeyboard/iPadShowKeyboard',
            'monaco-editor/esm/vs/editor/standalone/browser/quickOpen/quickOutline',
            'monaco-editor/esm/vs/editor/standalone/browser/quickOpen/gotoLine',
            'monaco-editor/esm/vs/editor/standalone/browser/quickOpen/quickCommand',
            // 主题
            'monaco-editor/esm/vs/editor/standalone/browser/themeService',
            // 格式化
            'monaco-editor/esm/vs/editor/standalone/browser/format/format',
            // 搜索
            'monaco-editor/esm/vs/editor/standalone/browser/find/find',
            // 代码折叠
            'monaco-editor/esm/vs/editor/standalone/browser/folding/folding',
            // 代码导航
            'monaco-editor/esm/vs/editor/standalone/browser/navigation/navigation',
            // 代码补全
            'monaco-editor/esm/vs/editor/standalone/browser/suggest/suggest',
            // 参数提示
            'monaco-editor/esm/vs/editor/standalone/browser/parameterHints/parameterHints',
            // 代码大纲
            'monaco-editor/esm/vs/editor/standalone/browser/outline/outline',
            // 调试支持
            'monaco-editor/esm/vs/editor/standalone/browser/debug/debug',
          ],
        },
      }
    }
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
      'monaco-editor': 'monaco-editor/esm/vs/editor/editor.api',
    },
  },
  optimizeDeps: {
    include: [
      // 核心编辑器
      'monaco-editor/esm/vs/editor/editor.api',
      'monaco-editor/esm/vs/editor/editor.worker',
      // 语言支持
      'monaco-editor/esm/vs/language/typescript/ts.worker',
      'monaco-editor/esm/vs/language/json/json.worker',
      'monaco-editor/esm/vs/language/css/css.worker',
      'monaco-editor/esm/vs/language/html/html.worker',
      'monaco-editor/esm/vs/basic-languages/python/python.worker',
      // 基础语言支持
      'monaco-editor/esm/vs/basic-languages/javascript/javascript.worker',
      'monaco-editor/esm/vs/basic-languages/typescript/typescript.worker',
      // 语言特性
      'monaco-editor/esm/vs/language/typescript/tsMode',
      'monaco-editor/esm/vs/language/json/jsonMode',
      'monaco-editor/esm/vs/language/css/cssMode',
      'monaco-editor/esm/vs/language/html/htmlMode',
      // 编辑器功能
      'monaco-editor/esm/vs/editor/standalone/browser/accessibilityHelp/accessibilityHelp',
      'monaco-editor/esm/vs/editor/standalone/browser/inspectTokens/inspectTokens',
      'monaco-editor/esm/vs/editor/standalone/browser/iPadShowKeyboard/iPadShowKeyboard',
      'monaco-editor/esm/vs/editor/standalone/browser/quickOpen/quickOutline',
      'monaco-editor/esm/vs/editor/standalone/browser/quickOpen/gotoLine',
      'monaco-editor/esm/vs/editor/standalone/browser/quickOpen/quickCommand',
      // 主题
      'monaco-editor/esm/vs/editor/standalone/browser/themeService',
      // 格式化
      'monaco-editor/esm/vs/editor/standalone/browser/format/format',
      // 搜索
      'monaco-editor/esm/vs/editor/standalone/browser/find/find',
      // 代码折叠
      'monaco-editor/esm/vs/editor/standalone/browser/folding/folding',
      // 代码导航
      'monaco-editor/esm/vs/editor/standalone/browser/navigation/navigation',
      // 代码补全
      'monaco-editor/esm/vs/editor/standalone/browser/suggest/suggest',
      // 参数提示
      'monaco-editor/esm/vs/editor/standalone/browser/parameterHints/parameterHints',
      // 代码大纲
      'monaco-editor/esm/vs/editor/standalone/browser/outline/outline',
      // 调试支持
      'monaco-editor/esm/vs/editor/standalone/browser/debug/debug',
    ],
    esbuildOptions: {
      target: 'es2020',
    },
  },
  define: {
    'process.env.NODE_ENV': JSON.stringify(process.env.NODE_ENV),
    'global': 'globalThis',
  },
})
