import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// 隔离验证专用配置：前端 5199 代理 /api 到隔离后端 8077（不碰用户真实 8000 实例）
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  optimizeDeps: {
    include: ['echarts'],
  },
  server: {
    port: 5199,
    strictPort: true,
    host: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8077',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
})
