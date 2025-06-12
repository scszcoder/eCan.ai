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
  server: {
    port: 3000,
    strictPort: true,
    host: true,
    fs: {
      strict: true,
      allow: ['..']
    }
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    emptyOutDir: true,
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor': ['react', 'react-dom']
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
    include: ['monaco-editor']
  },
  worker: {
    format: 'es',
    plugins: () => []
  },
  define: {
    'process.env.MONACO_EDITOR_CDN': JSON.stringify('/monaco-editor')
  },
  publicDir: 'public'
})
