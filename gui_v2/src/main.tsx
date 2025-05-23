import './i18n';
import ReactDOM from 'react-dom/client';
import App from './App';
import 'antd/dist/reset.css';
import './index.css';
import { initIPC } from './service/ipc/init';

// 初始化 IPC 服务
initIPC().then(() => {
    console.log('Start Init IPC');
}).catch(() => {
    console.warn('Start Init IPC failed or not in Qt environment');
});

ReactDOM.createRoot(document.getElementById('root')!).render(
    <App />
);
