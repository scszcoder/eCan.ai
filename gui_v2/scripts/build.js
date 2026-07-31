import { execSync } from 'child_process';
import { cpSync, existsSync, mkdirSync } from 'fs';
import { join } from 'path';

async function build() {
  try {
    // 构建项目
    console.log('Building project...');

    // 解析命令行参数（默认关闭 sourcemap，显式传参才开启）
    const args = process.argv.slice(2);
    const enableSourceMap = args.includes('--source-map') || args.includes('--sourcemap');
    process.env.VITE_SOURCEMAP = enableSourceMap ? 'true' : 'false';

    // 解析 --mode 参数（用于选择 .env.{mode} 文件）
    const modeArg = args.find(arg => arg.startsWith('--mode='));
    const mode = modeArg ? modeArg.split('=')[1] : null;

    // 设置环境变量以优化构建性能
    process.env.NODE_ENV = 'production';

    // 增加内存使用以避免内存不足
    const nodeOptions = process.env.NODE_OPTIONS || '';
    const memoryOptions = '--max-old-space-size=6144'; // 增加到 6GB

    // 只有没有设置内存选项时才添加
    if (!nodeOptions.includes('--max-old-space-size')) {
      process.env.NODE_OPTIONS = nodeOptions ? `${nodeOptions} ${memoryOptions}` : memoryOptions;
    }

    // 构建 vite 命令参数
    const viteArgs = ['build'];
    if (mode) {
      viteArgs.push(`--mode=${mode}`);
      console.log(`Using mode: ${mode}`);
    }
    if (enableSourceMap) {
      viteArgs.push('--sourcemap');
    }

    // 使用更高效的构建命令
    execSync(`vite ${viteArgs.join(' ')}`, {
      stdio: 'inherit',
      env: process.env,
      cwd: process.cwd()
    });

    // 复制 monaco-editor 文件到 dist 目录
    console.log('Copying monaco-editor files to dist...');
    const monacoSource = join(process.cwd(), 'public', 'monaco-editor');
    const monacoTarget = join(process.cwd(), 'dist', 'monaco-editor');
    
    if (existsSync(monacoSource)) {
      // 确保目标目录存在
      if (!existsSync(monacoTarget)) {
        mkdirSync(monacoTarget, { recursive: true });
      }
      
      // 复制 monaco-editor 文件
      cpSync(monacoSource, monacoTarget, { recursive: true });
      console.log('✅ Monaco-editor files copied successfully!');
    } else {
      console.warn('⚠️  Warning: monaco-editor source directory not found at:', monacoSource);
      console.warn('⚠️  Run "npm run copy-monaco" first to copy monaco-editor files to public directory');
    }

    console.log('Build completed successfully!');
  } catch (error) {
    console.error('Build failed:', error);
    process.exit(1);
  }
}

build(); 