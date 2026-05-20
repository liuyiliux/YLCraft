import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import AutoImport from 'unplugin-auto-import/vite'

export default defineConfig({
  plugins: [
    react(),
    AutoImport({
      imports: ['react', 'react-router-dom'],
      dts: 'src/auto-imports.d.ts',
    }),
  ],
  server: {
    host: '0.0.0.0',
    port: 3000,
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
        ws: true,
        configure: (proxy, options) => {
          proxy.on('proxyReq', (proxyReq, req, res) => {
            console.log(`[Proxy] ${req.method} ${req.url} -> http://127.0.0.1:8000${req.url}`);
          });
          proxy.on('error', (err, req, res) => {
            console.error('[Proxy Error]', err);
          });
        },
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        manualChunks: (id) => {
          if (id.includes('node_modules/antd')) {
            return 'antd'
          }
          if (id.includes('node_modules/@ant-design')) {
            return 'antd-icons'
          }
          if (id.includes('node_modules/react')) {
            return 'react-vendor'
          }
          if (id.includes('node_modules')) {
            return 'misc-vendor'
          }
        },
      },
    },
  },
})