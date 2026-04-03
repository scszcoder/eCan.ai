/**
 * Pre-build script: Bundles ESM code with esbuild for pkg compatibility.
 *
 * pkg cannot handle ESM dynamic imports (await import()), so we need to
 * pre-bundle the code into a CJS-compatible format before packaging.
 *
 * This script:
 * 1. Bundles index.js with esbuild (bundles all imports statically)
 * 2. Outputs to dist/bundle.cjs
 * 3. pkg then packages the bundled file instead of the source
 */
const { build } = require('esbuild');
const path = require('path');
const fs = require('fs');

const srcPath = path.join(__dirname, 'index.js');
const outPath = path.join(__dirname, 'dist', 'bundle.cjs');

// Ensure dist directory exists
const distDir = path.dirname(outPath);
if (!fs.existsSync(distDir)) {
  fs.mkdirSync(distDir, { recursive: true });
}

console.log(`[build-prepare] Bundling ${srcPath} -> ${outPath}`);

build({
  entryPoints: [srcPath],
  bundle: true,
  platform: 'node',
  target: 'node18',
  outfile: outPath,
  format: 'cjs',
  banner: {
    js: `#!/usr/bin/env node`,
  },
  external: ['fsevents'],
  sourcemap: false,
  minify: false,
})
  .then(() => {
    console.log('[build-prepare] Bundle created successfully');
  })
  .catch((err) => {
    console.error('[build-prepare] Bundle failed:', err);
    process.exit(1);
  });
