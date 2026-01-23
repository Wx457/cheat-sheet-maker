import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

// https://vite.dev/config/
export default defineConfig({
  base: '/static/',
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        // 首页：纯静态展示页
        main: resolve(__dirname, 'index.html'),
        // 渲染器：React App（给 Playwright 用）
        render: resolve(__dirname, 'render.html'),
      },
    },
  },
})
