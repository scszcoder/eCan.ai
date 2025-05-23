import './i18n';
import ReactDOM from 'react-dom/client';
import App from './App';
import 'antd/dist/reset.css';
import './index.css';
import { ipcClient } from './services/ipc';

// 初始化 IPC 服务
ipcClient.init().then(() => {
    console.log('Start IPC client initialized');
}).catch((error) => {
    console.warn('Start Failed to initialize IPC client:', error);
});

ReactDOM.createRoot(document.getElementById('root')!).render(
    <App />
);
