import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  // All built asset URLs will be prefixed with /digital-employee/
  // import.meta.env.BASE_URL === '/digital-employee/' at runtime
  base: '/digital-employee/',
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // In dev mode the app is served at /digital-employee/, so API calls
      // go to /digital-employee/api/... — rewrite by stripping the prefix.
      '/digital-employee/api': {
        target: 'http://localhost:8000',
        rewrite: (path) => path.replace('/digital-employee', ''),
        changeOrigin: true,
        ws: true,
      },
    },
  },
  build: {
    outDir: 'dist',
  },
})
