import { execSync } from 'child_process';

async function build() {
  try {
    // 构建项目
    console.log('Building project...');
    
    // 解析命令行参数（默认关闭 sourcemap，显式传参才开启）
    const args = process.argv.slice(2);
    const enableSourceMap = args.includes('--source-map') || args.includes('--sourcemap');
    process.env.VITE_SOURCEMAP = enableSourceMap ? 'true' : 'false';
    
    // 设置环境变量以优化构建性能
    process.env.NODE_ENV = 'production';
    
    // 增加内存使用以避免内存不足
    const nodeOptions = process.env.NODE_OPTIONS || '';
    const memoryOptions = '--max-old-space-size=6144'; // 增加到 6GB

    // 只有没有设置内存选项时才添加
    if (!nodeOptions.includes('--max-old-space-size')) {
      process.env.NODE_OPTIONS = nodeOptions ? `${nodeOptions} ${memoryOptions}` : memoryOptions;
    }

    // 使用更高效的构建命令
    execSync('vite build', { 
      stdio: 'inherit', 
      env: process.env,
      cwd: process.cwd()
    });

    console.log('Build completed successfully!');
  } catch (error) {
    console.error('Build failed:', error);
    process.exit(1);
  }
}

build(); 