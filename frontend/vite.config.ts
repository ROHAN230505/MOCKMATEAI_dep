import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
  },
  build: {
    // three.js forms one deliberately large chunk. It is loaded lazily and only
    // after the WebGL/device/reduced-motion checks in components/three/Backdrop
    // pass, so it never lands in the critical path — the default 500 kB warning
    // would just be noise on every build.
    chunkSizeWarningLimit: 1000,
  },
})
