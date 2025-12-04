import './i18n';
import ReactDOM from 'react-dom/client';
import App from './App';

// Suppress React deprecation warnings from third-party libraries
// These warnings come from bundled code (rc-util/antd/@flowgram.ai) and cannot be fixed externally
// Filter them at console.error level to keep the console clean
const originalConsoleError = console.error;
console.error = (...args: any[]) => {
  const msg = typeof args[0] === 'string' ? args[0] : '';
  // Suppress findDOMNode deprecation warning
  if (msg.includes('findDOMNode is deprecated')) {
    return;
  }
  // Suppress ReactDOM.render deprecation warning (backup filter)
  if (msg.includes('ReactDOM.render is no longer supported')) {
    return;
  }
  originalConsoleError.apply(console, args);
};

// 预设深色主题，避免白色闪烁
const setInitialTheme = () => {
    document.documentElement.style.setProperty('--bg-primary', '#0f172a');
    document.documentElement.style.setProperty('--text-primary', '#f8fafc');
    document.documentElement.style.setProperty('--bg-secondary', '#1e293b');
    document.documentElement.style.setProperty('--bg-tertiary', '#334155');
    document.documentElement.style.setProperty('--border-color', 'rgba(255, 255, 255, 0.1)');
};

// 立即Settings主题
setInitialTheme();

// AsyncRender应用，避免阻塞
const renderApp = () => {
    const root = ReactDOM.createRoot(document.getElementById('root')!);

    // 清除初始Load界面并Render应用
    const rootElement = document.getElementById('root')!;
    rootElement.innerHTML = ''; // 清除初始LoadContent

    root.render(<App />);
};

// 使用 requestIdleCallback 或 setTimeout 来DelayRender，让Browser有TimeProcess其他任务
if ('requestIdleCallback' in window) {
    requestIdleCallback(renderApp);
} else {
    setTimeout(renderApp, 0);
}
