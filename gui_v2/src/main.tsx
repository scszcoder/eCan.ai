import './i18n';
import ReactDOM from 'react-dom/client';
import App from './App';
// Configure Monaco Editor to use local files (must be imported before any Monaco usage)
import './modules/skill-editor/components/code-editor/monaco-config';
// Low performance detection - 在 React 渲染前尽早启用减少动画，避免低性能电脑闪烁
import './utils/lowPerformanceDetection';

// Suppress React deprecation warnings from third-party libraries in production
// These warnings come from bundled code (rc-util/antd/@flowgram.ai) and cannot be fixed externally
// Filter them at console.error level to keep the console clean for users
// if (process.env.NODE_ENV === 'production') {
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
    // Suppress synchronous unmount warning from third-party libraries (flowgram/flow-components)
    // These libraries internally use ReactDOM.createRoot and may trigger synchronous unmounts
    // during form node transitions, which causes this warning
    if (msg.includes('Attempted to synchronously unmount a root while React was already rendering')) {
      return;
    }
    // Suppress ResizeObserver loop warning (browser internal optimization, not a real error)
    if (msg.includes('ResizeObserver loop completed with undelivered notifications') ||
        msg.includes('ResizeObserver loop limit exceeded')) {
      return;
    }
    // Suppress antd Tooltip overlayStyle deprecation (third-party library API change)
    if (msg.includes('overlayStyle') && msg.includes('deprecated')) {
      return;
    }
    originalConsoleError.apply(console, args);
  };
// }

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

// 立即渲染应用
const root = ReactDOM.createRoot(document.getElementById('root')!);
root.render(<App />);
