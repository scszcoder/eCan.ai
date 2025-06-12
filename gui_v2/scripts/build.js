import fs from 'fs-extra';
import path from 'path';
import { fileURLToPath } from 'url';
import { execSync } from 'child_process';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function build() {
  try {
    // 1. 复制 Monaco Editor 文件
    console.log('Copying Monaco Editor files...');
    await execSync('node scripts/copy-monaco-files.js', { stdio: 'inherit' });

    // 2. 构建项目
    console.log('Building project...');
    await execSync('tsc -b && vite build', { stdio: 'inherit' });

    // 3. 确保 worker 文件在正确的位置
    const distDir = path.resolve(__dirname, '../dist');
    const publicDir = path.resolve(__dirname, '../public');
    const workersDir = path.join(distDir, 'workers');
    const vsDir = path.join(distDir, 'vs');

    console.log('Copying worker files to dist directory...');
    await fs.ensureDir(workersDir);
    await fs.copy(path.join(publicDir, 'workers'), workersDir);
    await fs.copy(path.join(publicDir, 'vs'), vsDir);

    console.log('Build completed successfully!');
  } catch (error) {
    console.error('Build failed:', error);
    process.exit(1);
  }
}

build(); 