import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import fs from 'fs-extra'

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
    }),
    {
      name: 'copy-monaco-workers',
      apply: 'build',
      async closeBundle() {
        const monacoPath = path.resolve(__dirname, 'node_modules/monaco-editor');
        const publicPath = path.resolve(__dirname, 'public/monaco-editor');
        const distPath = path.resolve(__dirname, 'dist/monaco-editor');
        
        // 确保目标目录存在
        await fs.ensureDir(publicPath);
        await fs.ensureDir(distPath);
        
        // 复制 worker 文件
        const workers = [
          'vs/language/typescript/ts.worker.js',
          'vs/language/json/json.worker.js',
          'vs/basic-languages/python/python.worker.js',
          'vs/editor/editor.worker.js'
        ];
        
        for (const worker of workers) {
          // 复制到 public 目录（开发环境使用）
          await fs.copy(
            path.resolve(monacoPath, worker),
            path.resolve(publicPath, worker)
          );
          
          // 复制到 dist 目录（生产环境使用）
          await fs.copy(
            path.resolve(monacoPath, worker),
            path.resolve(distPath, worker)
          );
        }
      }
    }
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
            'monaco-editor/esm/vs/basic-languages/python/python.worker',
            // 基础语言支持
            'monaco-editor/esm/vs/basic-languages/javascript/javascript.worker',
            'monaco-editor/esm/vs/basic-languages/typescript/typescript.worker',
            // 语言特性
            'monaco-editor/esm/vs/language/typescript/tsMode',
            'monaco-editor/esm/vs/language/json/jsonMode',
            // 编辑器功能
            'monaco-editor/esm/vs/editor/standalone/browser/accessibilityHelp/accessibilityHelp',
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
      'monaco-editor/esm/vs/basic-languages/python/python.worker',
      // 基础语言支持
      'monaco-editor/esm/vs/basic-languages/javascript/javascript.worker',
      'monaco-editor/esm/vs/basic-languages/typescript/typescript.worker',
      // 语言特性
      'monaco-editor/esm/vs/language/typescript/tsMode',
      'monaco-editor/esm/vs/language/json/jsonMode',
      // 编辑器功能
      'monaco-editor/esm/vs/editor/standalone/browser/accessibilityHelp/accessibilityHelp',
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
