import fs from 'fs-extra';
import path from 'path';
import { fileURLToPath } from 'url';
import fetch from 'node-fetch';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const MONACO_VERSION = '0.45.0';
const MONACO_CDN = `https://unpkg.com/monaco-editor@${MONACO_VERSION}/min/vs`;
const PUBLIC_DIR = path.resolve(__dirname, '../public');

async function copyMonacoFiles() {
  try {
    // 创建目录
    await fs.ensureDir(path.join(PUBLIC_DIR, 'vs'));
    await fs.ensureDir(path.join(PUBLIC_DIR, 'vs/base/worker'));
    await fs.ensureDir(path.join(PUBLIC_DIR, 'vs/language/json'));
    await fs.ensureDir(path.join(PUBLIC_DIR, 'vs/language/css'));
    await fs.ensureDir(path.join(PUBLIC_DIR, 'vs/language/html'));
    await fs.ensureDir(path.join(PUBLIC_DIR, 'vs/language/typescript'));
    await fs.ensureDir(path.join(PUBLIC_DIR, 'vs/language/python'));

    // 下载文件
    const files = [
      { url: `${MONACO_CDN}/base/worker/workerMain.js`, dest: 'vs/base/worker/workerMain.js' },
      { url: `${MONACO_CDN}/base/worker/simpleWorker.nls.js`, dest: 'vs/base/worker/simpleWorker.nls.js' },
      { url: `${MONACO_CDN}/language/json/jsonWorker.js`, dest: 'vs/language/json/jsonWorker.js' },
      { url: `${MONACO_CDN}/language/css/cssWorker.js`, dest: 'vs/language/css/cssWorker.js' },
      { url: `${MONACO_CDN}/language/html/htmlWorker.js`, dest: 'vs/language/html/htmlWorker.js' },
      { url: `${MONACO_CDN}/language/typescript/tsWorker.js`, dest: 'vs/language/typescript/tsWorker.js' },
      { url: `${MONACO_CDN}/language/python/pythonWorker.js`, dest: 'vs/language/python/pythonWorker.js' }
    ];

    for (const file of files) {
      const response = await fetch(file.url);
      const content = await response.text();
      await fs.writeFile(path.join(PUBLIC_DIR, file.dest), content);
      console.log(`Copied ${file.dest}`);
    }

    console.log('Monaco Editor files copied successfully!');
  } catch (error) {
    console.error('Error copying Monaco Editor files:', error);
    process.exit(1);
  }
}

copyMonacoFiles(); 