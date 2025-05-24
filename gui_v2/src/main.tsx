import './i18n';
import ReactDOM from 'react-dom/client';
import App from './App';
import 'antd/dist/reset.css';
import './index.css';
import { IPCClient } from './services/ipc/client';

// 初始化 IPC 服务
IPCClient.getInstance();

ReactDOM.createRoot(document.getElementById('root')!).render(
    <App />
);
