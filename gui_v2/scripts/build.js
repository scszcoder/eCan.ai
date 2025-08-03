import { execSync } from 'child_process';

async function build() {
  try {
    // 构建项目
    console.log('Building project...');
    
    // 解析命令行参数
    const args = process.argv.slice(2);
    if (args.includes('--no-source-map')) {
      process.env.VITE_SOURCEMAP = 'false';
    } else {
      process.env.VITE_SOURCEMAP = 'true'; // 启用 sourcemap 以便调试
    }
    
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