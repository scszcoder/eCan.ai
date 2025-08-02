import { execSync } from 'child_process';

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
    // 解析命令行参数
    const args = process.argv.slice(2);
    if (args.includes('--no-source-map')) {
      process.env.VITE_SOURCEMAP = 'false';
    }
    // Set Node.js memory options for large builds
    const nodeOptions = process.env.NODE_OPTIONS || '';
    const memoryOptions = '--max-old-space-size=8192';

    // Only add memory options if not already present
    if (!nodeOptions.includes('--max-old-space-size')) {
      process.env.NODE_OPTIONS = nodeOptions ? `${nodeOptions} ${memoryOptions}` : memoryOptions;
    }

    execSync('vite build', { stdio: 'inherit', env: process.env });

    console.log('Build completed successfully!');
  } catch (error) {
    console.error('Build failed:', error);
    process.exit(1);
  }
}

build(); 