import './i18n';
import ReactDOM from 'react-dom/client';
import App from './App';

// 预设深色主题，避免白色闪烁
document.documentElement.style.setProperty('--bg-primary', '#0f172a');
document.documentElement.style.setProperty('--text-primary', '#f8fafc');
document.documentElement.style.setProperty('--bg-secondary', '#1e293b');
document.documentElement.style.setProperty('--bg-tertiary', '#334155');
document.documentElement.style.setProperty('--border-color', 'rgba(255, 255, 255, 0.1)');

const root = ReactDOM.createRoot(document.getElementById('root')!);

// 清除初始加载界面并渲染应用
const rootElement = document.getElementById('root')!;
rootElement.innerHTML = ''; // 清除初始加载内容

root.render(<App />);
