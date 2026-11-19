import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/auth':     'http://127.0.0.1:8000',
      '/api':      'http://127.0.0.1:8000',
      '/alerts':   'http://127.0.0.1:8000',
      '/devices':  'http://127.0.0.1:8000',
      '/readings': 'http://127.0.0.1:8000',
      '/wards':    'http://127.0.0.1:8000',
      '/handover': 'http://127.0.0.1:8000',
      '/stats':    'http://127.0.0.1:8000',
      '/ws': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
      },
    },
  },
})
