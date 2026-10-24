import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// The server serves the built app from frontend/dist and the API under /api/*
// at the same origin. In development, proxy /api to local FastAPI.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // Shared domain types remain single-sourced in repo-root /contracts.
      '@contracts': fileURLToPath(new URL('../contracts/index.ts', import.meta.url)),
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
