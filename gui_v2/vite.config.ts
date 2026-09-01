import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
//
// Runtime-based configuration (no build-time product differentiation):
//
// Development:
//   npm run dev                # vite (默认开发模式)
//
// Production build:
//   npm run build              # 统一构建，包含所有认证方式
//   VITE_PLATFORM=web npm run build
//
// Env files:
//   .env              - shared defaults
//   .env.local        - personal secrets (gitignored, overrides all)

export default defineConfig(() => {
  // Platform: desktop (default) or web
  // Web also requires VITE_BASE for subpath deployments
  const platform = process.env.VITE_PLATFORM || 'desktop';
  const basePath = platform === 'desktop'
    ? './'
    : (process.env.VITE_BASE || '/app/gui-v2/');

  // Compile-time constants
  const defineConstants = {
    __PLATFORM__: JSON.stringify(platform),
  };

  const localServerPort = process.env.VITE_LOCAL_SERVER_PORT || '4668';
  const localServerTarget = `http://localhost:${localServerPort}`;

  console.log(`[Build Config] Platform: ${platform}, Base: ${basePath}`);

  return {
    define: defineConstants,
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
      // vite proxy intentionally does NOT include `/api/config`:
      //   - desktop dev: AppConfigProvider uses apiRouter.execute({method:
      //     'getAppConfig'}) → /graphql (proxied above) → IPC handler. No
      //     HTTP fetch to /api/config involved.
      //   - web dev: served by `python web_server.py` (not vite), so the
      //     proxy here is irrelevant.
      // Adding /api/config here would be tempting but actually routes the
      // request to LocalServer (not web_server), which serves nothing
      // for that path — do not add.
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
          // Split vendor into focused chunks so the initial bundle doesn't
          // carry every UI library. The previous "react → vendor; rest of
          // node_modules → vendor" rule stuffed 12+ MB into one chunk
          // (vendor-C2IlIxh5.js, gzip 3.5 MB), well past Vite's 5 MB warning
          // line. Splitting cuts first-paint JS and lets Rollup cache the
          // largest chunks (monaco, flowgram, sigma) independently.
          manualChunks: (id) => {
            // Monaco editor — only loaded by the skill editor and code-style
            // pages. Split first because it's the single biggest dep.
            if (id.includes('monaco-editor') || id.includes('@monaco-editor')) {
              return 'monaco';
            }
            // React core — present on every page; cache-friendly.
            if (id.includes('node_modules/react/') ||
                id.includes('node_modules/react-dom/') ||
                id.includes('node_modules/scheduler/')) {
              return 'react-vendor';
            }
            // @flowgram.ai is huge (~3 MB) and only used by the skill editor
            // flow-canvas page. Splitting it means non-skill pages never
            // pay for it.
            if (id.includes('@flowgram.ai')) {
              return 'flowgram';
            }
            // Graph visualization stack — only the graph/Knowledge-port pages.
            if (id.includes('@react-sigma') ||
                id.includes('graphology') ||
                id.includes('/sigma/')) {
              return 'sigma';
            }
            // UI component libraries — used across many pages; cache-friendly.
            if (id.includes('@ant-design') ||
                id.includes('@douyinfe/semi-ui') ||
                id.includes('@douyinfe/semi-icons')) {
              return 'ui-vendor';
            }
            // Emotion (CSS-in-JS) — only needed when components actually
            // style themselves; split to keep it from coupling with react-vendor.
            if (id.includes('@emotion/')) {
              return 'emotion';
            }
            // Anything else in node_modules.
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
        // graphology layouts used by LightRAGPorted/graph (prebundle to avoid 504)
        'graphology-layout',
        'graphology-layout-force',
        'graphology-layout-forceatlas2',
        'graphology-layout-noverlap',
        // markdown + syntax highlighting used by LightRAGPorted (prebundle to avoid 504)
        'react-markdown',
        'remark-gfm',
        'react-syntax-highlighter',
        'react-syntax-highlighter/dist/cjs/styles/prism',
        'lucide-react',
        // emotion - used in Tasks and other pages, must be pre-bundled to avoid 504
        '@emotion/react',
        '@emotion/styled',
        // i18n
        'react-i18next',
        'i18next',
        // lodash-es (used via @/components/Common/SearchFilter; lazy-discovered in Vehicles/Chat)
        'lodash-es',
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
