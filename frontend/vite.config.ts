/// <reference types="vitest/config" />
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import react from '@vitejs/plugin-react';
import { defineConfig, type Plugin } from 'vite';

const backend = 'http://127.0.0.1:8765';

/** Emits sw/sw.js as /sw.js with the list of files to precache and a version stamp. */
function serviceWorker(): Plugin {
  return {
    name: 'closet-service-worker',
    apply: 'build',
    generateBundle(_options, bundle) {
      const files = Object.keys(bundle).filter((f) => !f.endsWith('.map'));
      const shell = ['/', ...files.map((f) => `/${f}`)].sort();
      const extra = ['/manifest.webmanifest', '/icons/apple-touch-icon.png', '/icons/icon-192.png',
        '/icons/icon-512.png', '/icons/favicon-32.png'];
      const precache = [...shell, ...extra];
      const version = createHash('sha256').update(precache.join('\n')).digest('hex').slice(0, 12);
      const source = readFileSync(resolve(import.meta.dirname, 'sw/sw.js'), 'utf8')
        .replace('self.__PRECACHE__', JSON.stringify(precache))
        .replace('self.__VERSION__', JSON.stringify(version));
      this.emitFile({ type: 'asset', fileName: 'sw.js', source });
    },
  };
}

export default defineConfig({
  plugins: [react(), serviceWorker()],
  build: {
    outDir: '../backend/closet/web',
    emptyOutDir: true,
    target: 'es2020',
  },
  server: {
    proxy: {
      '/api': backend,
      '/media': backend,
    },
  },
  test: {
    include: ['src/**/*.test.ts'],
    environment: 'node',
  },
});
