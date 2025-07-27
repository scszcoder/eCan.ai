import fs from 'fs-extra';
import path from 'path';
import { fileURLToPath } from 'url';
import { execSync } from 'child_process';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function build() {
  try {
    // // 确保monaco-editor文件存在
    // console.log('Copying Monaco Editor files...');
    // const monacoSource = path.join(__dirname, '../node_modules/monaco-editor/min/vs');
    // const monacoDest = path.join(__dirname, '../public/monaco-editor/vs');
    
    // if (await fs.pathExists(monacoSource)) {
    //   await fs.ensureDir(path.dirname(monacoDest));
    //   await fs.copy(monacoSource, monacoDest);
    //   console.log('Monaco Editor files copied successfully!');
    // } else {
    //   console.warn('Monaco Editor files not found in node_modules, skipping copy...');
    // }

    // 构建项目
    console.log('Building project...');
    // Skip TypeScript type checking during build
    await execSync('vite build', { stdio: 'inherit' });

    console.log('Build completed successfully!');
  } catch (error) {
    console.error('Build failed:', error);
    process.exit(1);
  }
}

build(); 