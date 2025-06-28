import { HashRouter, Routes, Route } from 'react-router-dom';
import { ConfigProvider, theme, App as AntdApp } from 'antd';
import { routes, RouteConfig } from './routes';
import { ThemeProvider, useTheme } from './contexts/ThemeContext';
import { LanguageProvider } from './contexts/LanguageContext';
import { getAntdLocale } from './i18n';
import { pageRefreshManager } from './services/events/PageRefreshManager';
import { logger, LogLevel } from './utils/logger';
import './styles/global.css';
import 'antd/dist/reset.css';
import './index.css';
import { set_ipc_api } from './services/ipc_api';
import { createIPCAPI } from './services/ipc';
import { protocolHandler } from './pages/Chat/utils/protocolHandler';

// 初始化应用
const initializeApp = () => {
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
  set_ipc_api(createIPCAPI());

  // 初始化页面刷新管理器
  pageRefreshManager.initialize();

  // 初始化协议处理器
  protocolHandler.init();
};

// 配置 React Router future flags
// const router = {
//     future: {
//         v7_startTransition: true,
//         v7_relativeSplatPath: true
//     }
// };

// 自定义主题配置
const getThemeConfig = (isDark: boolean) => ({
    token: {
        colorPrimary: '#3b82f6',
        colorSuccess: '#22c55e',
        colorWarning: '#eab308',
        colorError: '#ef4444',
        colorInfo: '#0ea5e9',
        borderRadius: 8,
        wireframe: false,
    },
    algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
    components: {
        Layout: {
            bodyBg: isDark ? '#0f172a' : '#f0f2f5',
            headerBg: isDark ? '#1e293b' : '#ffffff',
            siderBg: isDark ? '#1e293b' : '#ffffff',
        },
        Menu: {
            darkItemBg: isDark ? '#1e293b' : '#ffffff',
            darkItemSelectedBg: isDark ? '#334155' : '#f0f2f5',
            darkItemHoverBg: isDark ? '#334155' : '#f0f2f5',
        },
        Card: {
            colorBgContainer: isDark ? '#1e293b' : '#ffffff',
            colorBorderSecondary: isDark ? '#334155' : '#f0f0f0',
        },
        Button: {
            colorPrimary: '#3b82f6',
            colorPrimaryHover: '#2563eb',
        },
        Input: {
            colorBgContainer: isDark ? '#334155' : '#ffffff',
            colorBorder: isDark ? '#475569' : '#d9d9d9',
        },
        Table: {
            colorBgContainer: isDark ? '#1e293b' : '#ffffff',
            headerBg: isDark ? '#1e293b' : '#fafafa',
            headerColor: isDark ? '#f8fafc' : '#000000',
            rowHoverBg: isDark ? '#334155' : '#fafafa',
        },
    },
});

// 递归渲染路由
const renderRoutes = (routes: RouteConfig[]) => {
    return routes.map((route) => (
        <Route key={route.path} path={route.path} element={route.element}>
            {route.children && renderRoutes(route.children)}
        </Route>
    ));
};

const AppContent = () => {
    const { theme: currentTheme } = useTheme();
    const isDark = currentTheme === 'dark' || (currentTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);

    return (
        <ConfigProvider
            locale={getAntdLocale()}
            theme={getThemeConfig(isDark)}
        >
            <AntdApp>
                <HashRouter>
                    <Routes>
                        {renderRoutes(routes)}
                    </Routes>
                </HashRouter>
            </AntdApp>
        </ConfigProvider>
    );
};

function App() {
    // 初始化应用
    initializeApp();

    return (
        <ThemeProvider>
            <LanguageProvider>
                <AppContent />
            </LanguageProvider>
        </ThemeProvider>
    );
}

export default App;
