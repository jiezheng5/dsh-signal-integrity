import { defineConfig } from 'tsdown'

/**
 * Bundle the tsc output into one ESM entry. Every `@deepseek-ai/*` import
 * stays external so the plugin shares the DSH installation's single cordis
 * instance instead of carrying a duplicate.
 */
export default defineConfig({
  entry: ['lib/types/index.js'],
  outDir: 'lib',
  format: ['esm'],
  platform: 'node',
  target: 'es2024',
  fixedExtension: false,
  dts: false,
  clean: false,
  external: [/^@deepseek-ai\//],
})
