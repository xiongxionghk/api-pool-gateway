import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/admin': {
        target: 'http://localhost:8899',
        changeOrigin: true,
      },
      '/v1': {
        target: 'http://localhost:8899',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
