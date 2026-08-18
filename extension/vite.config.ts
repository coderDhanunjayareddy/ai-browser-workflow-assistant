import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { crx } from '@crxjs/vite-plugin'
import manifest from './manifest.json'

export default defineConfig({
  define: {
    __BACKEND_URL__: JSON.stringify(process.env.VITE_BACKEND_URL || 'http://localhost:8000'),
    __APP_VERSION__: JSON.stringify(process.env.VITE_APP_VERSION || manifest.version),
    __BUILD_COMMIT__: JSON.stringify(process.env.VITE_BUILD_COMMIT || 'dev'),
    __BUILD_ID__: JSON.stringify(process.env.VITE_BUILD_ID || 'local-dev'),
  },
  plugins: [
    react(),
    crx({ manifest }),
  ],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
