import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  build: {
    assetsInlineLimit: 0,
    chunkSizeWarningLimit: 6000,
    rollupOptions: {
      output: {
        manualChunks: {
          'renderer-vega': ['vega', 'vega-lite', 'vega-embed', 'vega-interpreter'],
          'renderer-plotly': ['plotly.js-dist-min'],
          'renderer-echarts': ['echarts'],
          duckdb: ['@duckdb/duckdb-wasm', 'apache-arrow'],
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['src/test/setup.ts'],
    exclude: ['e2e/**', 'node_modules/**', 'dist/**'],
    css: false,
  },
});
