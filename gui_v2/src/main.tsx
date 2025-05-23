import './i18n';
import ReactDOM from 'react-dom/client';
import App from './App';
import 'antd/dist/reset.css';
import './index.css';
import { initIPC } from './service/ipc/init';

// 初始化 IPC 服务
initIPC().then((success) => {
    if (success) {
        console.log('IPC initialized successfully');
    } else {
        console.warn('IPC initialization failed or not in Qt environment');
    }
});

// 检查是否在 Qt WebEngine 环境中
if (!window.qt?.webChannelTransport) {
    console.warn('Not running in Qt WebEngine environment');
} else {
    console.log('Running in Qt WebEngine environment');
}

ReactDOM.createRoot(document.getElementById('root')!).render(
    <App />
);
