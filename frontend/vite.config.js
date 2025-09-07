import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    proxy: {
      '/api': 'http://localhost:8000', // פרוקסי לקריאות API
      '/ws': {
        target: 'ws://localhost:8000', // פרוקסי ל-WebSocket
        ws: true
      }
    }
  }
})
