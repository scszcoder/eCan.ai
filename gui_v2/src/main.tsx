import './i18n';
import ReactDOM from 'react-dom/client';
import App from './App';
import 'antd/dist/reset.css';
import './index.css';
import { IPCClient } from './services/ipc/client';
import { logger, LogLevel } from './utils/logger';

// 根据环境设置日志等级
const isDevelopment = process.env.NODE_ENV === 'development';

// 打印当前环境信息
console.log('Current NODE_ENV:', process.env.NODE_ENV);
console.log('Is development:', isDevelopment);

if (isDevelopment) {
    // 开发环境：显示所有日志
    logger.setLevel(LogLevel.DEBUG);
    console.log('Set log level to:', LogLevel[logger.getLevel()]);
} else {
    // 生产环境：只显示信息、警告和错误
    logger.setLevel(LogLevel.INFO);
    logger.info('Running in production mode, debug logs disabled');
}

// 初始化 IPC 服务
IPCClient.getInstance();

ReactDOM.createRoot(document.getElementById('root')!).render(
    <App />
);
