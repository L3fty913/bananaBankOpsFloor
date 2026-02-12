import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    port: 5173,
    proxy: {
      '/workspace': {
        target: 'http://localhost:8790',
        changeOrigin: true,
      },
      '/healthz': {
        target: 'http://localhost:8790',
        changeOrigin: true,
      },
    },
  },
});
