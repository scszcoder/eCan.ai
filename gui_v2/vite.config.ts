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
      // 'Cross-Origin-Embedder-Policy': 'require-corp',
      // 'Cross-Origin-Opener-Policy': 'same-origin'
    }
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    emptyOutDir: true,
    sourcemap: process.env.VITE_SOURCEMAP === 'true', // 启用 sourcemap 以便调试
    // 使用更保守的构建选项
    minify: 'esbuild', // 暂时禁用压缩以避免问题
    rollupOptions: {
      // 优化并行处理
      maxParallelFileOps: 1, // 减少并行处理以避免内存问题
      output: {
        manualChunks: (id) => {
          // 将 Monaco Editor 相关代码分离到单独的 chunk
          if (id.includes('monaco-editor') || id.includes('@monaco-editor')) {
            return 'monaco';
          }
          // 将 React 相关代码分离到 vendor chunk
          if (id.includes('react') || id.includes('react-dom')) {
            return 'vendor';
          }
          // 其他第三方库
          if (id.includes('node_modules')) {
            return 'vendor';
          }
        }
      }
    },
    chunkSizeWarningLimit: 5000, // 提高警告阈值到 5MB
    // 优化动态导入
    commonjsOptions: {
      include: [/node_modules/],
      transformMixedEsModules: true
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
      'monaco-editor/esm/vs/language/typescript/ts.worker',
      'react-split-pane',
      'react',
      'react-dom',
      'antd',
      '@ant-design/icons',
      '@douyinfe/semi-ui',
      'monaco-editor',
      // react-sigma graph stack - prebundle to avoid Outdated Optimize Dep 504
      '@react-sigma/core',
      '@react-sigma/graph-search',
      '@react-sigma/layout-circular',
      '@react-sigma/layout-random',
      '@react-sigma/layout-noverlap',
      '@react-sigma/layout-force',
      '@react-sigma/layout-forceatlas2',
      'graphology',
      'sigma',
      '@sigma/node-border',
      '@sigma/edge-curve'
    ],
    exclude: [],
    // Force re-optimize after dependency changes to avoid stale optimized deps
    force: true
  },
  worker: {
    format: 'es',
    plugins: () => []
  },
  publicDir: 'public'
})
