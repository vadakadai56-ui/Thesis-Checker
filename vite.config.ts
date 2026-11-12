import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vitest/config';

// The Content-Security-Policy from BUILD_PROMPT §10. In production it is sent by the
// host (public/_headers, stage 7); here it is also sent by `vite preview`, so the
// browser tests prove that Pyodide really works under it.
export const CSP = [
  "default-src 'self'",
  "script-src 'self' 'wasm-unsafe-eval'",
  "worker-src 'self' blob:",
  "connect-src 'self'",
  "img-src 'self' data: blob:",
  "style-src 'self' 'unsafe-inline'",
  "font-src 'self'",
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
  "frame-ancestors 'none'",
].join('; ');

export default defineConfig({
  plugins: [svelte()],
  worker: { format: 'es' },
  build: { target: 'es2022' },
  preview: {
    port: 4173,
    strictPort: true,
    headers: {
      'Content-Security-Policy': CSP,
      'X-Content-Type-Options': 'nosniff',
      'Referrer-Policy': 'no-referrer',
    },
  },
  test: { include: ['src/**/*.test.ts'] },
});
