import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const resolveFromConfig = (relPath: string): string =>
  decodeURIComponent(new URL(relPath, import.meta.url).pathname).replace(
    /^\/([A-Za-z]:)/,
    '$1',
  )

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      vue: resolveFromConfig('./node_modules/vue'),
      '@': resolveFromConfig('./src'),
      '@plugins': resolveFromConfig('../plugins'),
    },
  },
  server: {
    port: 5173,
    fs: {
      allow: ['..'],
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8080',
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
