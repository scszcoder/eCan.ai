'use strict';

const fs = require('node:fs');
const path = require('node:path');

const projectRoot = path.resolve(__dirname, '..');
const source = path.join(projectRoot, 'node_modules', '.prisma', 'client');
const destination = path.join(projectRoot, 'prisma-client');
const wrapperDirectory = path.join(projectRoot, 'node_modules', '@prisma', 'client');

if (!fs.existsSync(path.join(source, 'index.js'))) {
  throw new Error(`Generated Prisma client is missing: ${source}`);
}

fs.rmSync(destination, { recursive: true, force: true });
fs.cpSync(source, destination, { recursive: true });

for (const fileName of ['default.js', 'index.js']) {
  const filePath = path.join(wrapperDirectory, fileName);
  const content = fs.readFileSync(filePath, 'utf8');
  if (content.includes("require('../../../prisma-client/default')")) continue;
  const updated = content.replace(
    "require('.prisma/client/default')",
    "require('../../../prisma-client/default')",
  );
  if (updated === content) {
    throw new Error(`Prisma wrapper was not updated: ${filePath}`);
  }
  fs.writeFileSync(filePath, updated);
}

console.log('Relocated generated Prisma client to prisma-client/');