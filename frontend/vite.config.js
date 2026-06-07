import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3332,
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: 'http://localhost:3331',
        changeOrigin: true
      },
      '/socket.io': {
        target: 'http://localhost:3331',
        changeOrigin: true,
        ws: true
      }
    }
  }
})
