import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
// For PyInstaller bundled apps, use relative path './' instead of absolute '/app/gui-v2/'
// This allows the HTML to correctly reference assets when loaded via file:// protocol

export default defineConfig(({ mode }) => {
  // Build target determines the base path:
  //   VITE_TARGET=web   → '/app/gui-v2/'  (Nginx web/Docker deployment)
  //   VITE_TARGET=desktop (default) → './'  (PyInstaller, file:// protocol)
  // You can also override directly with VITE_BASE for custom deployments.
  const target = process.env.VITE_TARGET || 'desktop';
  const defaultBase = target === 'web' ? '/app/gui-v2/' : './';
  const basePath = process.env.VITE_BASE || (mode === 'production' ? defaultBase : '/');
  const localServerPort = process.env.VITE_LOCAL_SERVER_PORT || '4668';
  const localServerTarget = `http://localhost:${localServerPort}`;

  return {
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
  base: basePath,
  server: {
    port: 3000,
    strictPort: true, // 如果端口被占用，则直接退出
    host: true, // 监听所有地址
    proxy: {
      '/graphql': {
        target: localServerTarget,
        changeOrigin: true,
      },
      '/ws': {
        target: localServerTarget,
        ws: true,
        changeOrigin: true,
      },
    },
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
    minify: 'esbuild', // 使用 esbuild 进行压缩
    rollupOptions: {
      // 优化并行处理
      // maxParallelFileOps: 20, // 恢复默认并行处理 (默认: 20)
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
    // Pre-scan lazy-route/page modules so third-party deps are discovered at startup
    // instead of being discovered on first navigation (which can cause 504 Outdated Optimize Dep).
    entries: [
      'index.html',
      'src/main.tsx',
      'src/routes/**/*.tsx',
      'src/pages/**/*.tsx',
      'src/pages/**/*.ts'
    ],
    include: [
      'monaco-editor/esm/vs/editor/editor.worker',
      'monaco-editor/esm/vs/language/json/json.worker',
      'monaco-editor/esm/vs/language/css/css.worker',
      'monaco-editor/esm/vs/language/html/html.worker',
      'monaco-editor/esm/vs/language/typescript/ts.worker',
      'split-pane-react',
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
      '@sigma/edge-curve',
      // emotion - used in Tasks and other pages, must be pre-bundled to avoid 504
      '@emotion/react',
      '@emotion/styled',
      // i18n
      'react-i18next',
      'i18next',
      // date
      'dayjs',
      'dayjs/plugin/relativeTime',
      'dayjs/plugin/isoWeek',
      'dayjs/plugin/weekday',
      'dayjs/plugin/isSameOrBefore',
      'dayjs/plugin/isSameOrAfter',
      'dayjs/plugin/isBetween',
      'dayjs/locale/en',
      'dayjs/locale/zh-cn'
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
  };
})
