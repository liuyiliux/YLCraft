import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import AutoImport from 'unplugin-auto-import/vite'

export default defineConfig(({ mode }) => {
  const apiProxyTarget = loadEnv(mode, '.', '').VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000'

  return {
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
        target: apiProxyTarget,
        changeOrigin: true,
        secure: false,
        ws: true,
        configure: (proxy, options) => {
          proxy.on('proxyReq', (proxyReq, req, res) => {
            console.log(`[Proxy] ${req.method} ${req.url} -> ${apiProxyTarget}${req.url}`);
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
    chunkSizeWarningLimit: 1600,
    rollupOptions: {
      output: {
        manualChunks: (id: string) => {
          const normalized = id.replace(/\\/g, '/')
          if (normalized.indexOf('node_modules') >= 0) {
            return 'vendor'
          }
        },
      },
    },
  },
  }
})
