import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  base: './',  // 使用相对路径
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    // 确保资源文件名包含哈希值，并禁用代码分割
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]',
        manualChunks: undefined
      }
    }
  },
  server: {
    fs: {
      // 允许访问项目根目录之外的文件
      strict: false
    },
    headers: {
      'Access-Control-Allow-Origin': '*'
    }
  }
})
