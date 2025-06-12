import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// Monaco Editor CDN 配置
const MONACO_CDN = 'https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs';

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
  base: './', // 使用相对路径，支持 file:// 协议
  server: {
    port: 3000,
    strictPort: true, // 如果端口被占用，则直接退出
    host: true, // 监听所有地址
    fs: {
      // 允许访问项目根目录之外的文件
      strict: true,
      allow: ['..']
    },
    headers: {
      'Cross-Origin-Embedder-Policy': 'require-corp',
      'Cross-Origin-Opener-Policy': 'same-origin'
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
        manualChunks: {
          'vendor': ['react', 'react-dom'],
          'monaco-editor': ['monaco-editor']
        }
      }
    }
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src')
    }
  },
  optimizeDeps: {
    include: [
      'monaco-editor/esm/vs/editor/editor.worker',
      'monaco-editor/esm/vs/language/json/json.worker',
      'monaco-editor/esm/vs/language/css/css.worker',
      'monaco-editor/esm/vs/language/html/html.worker',
      'monaco-editor/esm/vs/language/typescript/ts.worker'
    ],
  },
  worker: {
    format: 'es',
    plugins: () => []
  },
  define: {
    'process.env.MONACO_EDITOR_CDN': JSON.stringify(MONACO_CDN)
  },
  publicDir: 'public'
})
