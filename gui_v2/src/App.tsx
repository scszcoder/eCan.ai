import React from 'react';
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
import { useUserStore } from './stores/userStore';
import { useAgentStore } from './stores/agentStore';
import { logoutManager } from './services/LogoutManager';
import { initializePlatform } from './config/platform';
import { initializeStoreSync, cleanupStoreSync } from './services/storeSync';
import { orgDataSyncService } from './services/OrgDataSyncService';
import './utils/videoSupport'; // Initialize video support check on page load



// 配置 React Router future flags
// const router = {
//     future: {
//         v7_startTransition: true,
//         v7_relativeSplatPath: true
//     }
// };

// 自定义主题配置 - 标准 Ant Design 架构
const getThemeConfig = (isDark: boolean) => ({
    token: {
        // 品牌色
        colorPrimary: '#3b82f6',
        colorSuccess: '#22c55e',
        colorWarning: '#eab308',
        colorError: '#ef4444',
        colorInfo: '#0ea5e9',
        borderRadius: 8,
        wireframe: false,
        // 明确设置背景色，使用原来的配色方案
        ...(isDark ? {
            colorBgLayout: '#0f172a',      // 深蓝黑色页面背景（原来的颜色）
            colorBgContainer: '#1e293b',   // 深蓝灰色容器背景（原来的颜色）
            colorBgElevated: '#1e293b',    // 深蓝灰色浮层背景
        } : {
            colorBgLayout: '#f0f2f5',      // 浅灰色页面背景
            colorBgContainer: '#ffffff',   // 白色容器背景
            colorBgElevated: '#ffffff',    // 白色浮层背景
        }),
    },
    algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
    components: {
        Layout: {
            // Layout 组件的背景色，使用原来的配色方案
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
    // Initialize platform at app mount so IPC gating flags are correct
    React.useEffect(() => {
        try {
            initializePlatform();
        } catch (e) {
            // eslint-disable-next-line no-console
            console.warn('[App] Failed to initialize platform, defaulting to env-based config:', e);
        }
    }, []);
    const { theme: currentTheme } = useTheme();
    const isDark = currentTheme === 'dark' || (currentTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);

    // 应用全局背景色到 body 和 #root
    React.useEffect(() => {
        const bgColor = isDark ? '#0f172a' : '#f0f2f5';  // 恢复原来的深蓝黑色
        const textColor = isDark ? '#f8fafc' : '#000000';
        
        document.body.style.backgroundColor = bgColor;
        document.body.style.color = textColor;
        
        const root = document.getElementById('root');
        if (root) {
            root.style.backgroundColor = bgColor;
        }
    }, [isDark]);

    // Note: avoid immediate fetch on username to prevent racing backend init; we poll readiness below

    // 初始化组织数据同步服务（后台监听器）
    React.useEffect(() => {
        orgDataSyncService.initialize();
        
        return () => {
            orgDataSyncService.cleanup();
        };
    }, []);

    // Register App-level cleanup for logout
    React.useEffect(() => {
        logoutManager.registerCleanup({
            name: 'App',
            cleanup: () => {
                try {
                    logger.info('[App] Cleaning up for logout...');

                    // 清理用户状态
                    const userStore = useUserStore.getState();
                    if (userStore && typeof userStore.setUsername === 'function') {
                        userStore.setUsername(null);
                        logger.debug('[App] User state cleared');
                    }

                    // 清理 agents 状态
                    const agentStore = useAgentStore.getState();
                    if (agentStore && typeof agentStore.setAgents === 'function') {
                        agentStore.setAgents([]);
                        logger.debug('[App] Agent state cleared');
                    }

                    // 工具状态清理已移至 Tools 页面按需处理
                    
                    // 清理 store 同步监听器
                    cleanupStoreSync();
                    logger.debug('[App] Store sync listeners cleaned up');

                    // 清理组织数据同步服务
                    orgDataSyncService.cleanup();
                    logger.debug('[App] Org data sync service cleaned up');

                    logger.info('[App] App cleanup completed');
                } catch (error) {
                    logger.error('[App] Error during cleanup:', error);
                }
            },
            priority: 30 // 较低优先级，在其他服务清理后执行
        });
    }, []);

    // Tools are now loaded on-demand when accessing Tools page or skill editor
    // This improves startup performance by removing unnecessary preloading

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
    const [isInitialized, setIsInitialized] = React.useState(false);

    React.useEffect(() => {
        // 同步初始化关键服务，异步初始化其他服务
        try {
            // 初始化 IPC 服务（同步）- 必须在平台检测之前
            set_ipc_api(createIPCAPI());

            // 初始化平台配置（同步）- 依赖 IPC API 进行平台检测
            initializePlatform();

            // 异步初始化其他服务
            const initOtherServices = async () => {
                try {
                    // 初始化页面刷新管理器
                    pageRefreshManager.initialize();

                    // 初始化协议处理器
                    protocolHandler.init();
                    
                    // 初始化 store 同步监听器
                    initializeStoreSync();

                    // 根据环境设置日志等级
                    const isDevelopment = process.env.NODE_ENV === 'development';

                    if (isDevelopment) {
                        logger.setLevel(LogLevel.DEBUG);
                    } else {
                        logger.setLevel(LogLevel.INFO);
                        logger.info('Running in production mode, debug logs disabled');
                    }
                } catch (error) {
                    console.error('Failed to initialize other services:', error);
                }
            };

            initOtherServices();
            setIsInitialized(true);
        } catch (error) {
            console.error('Failed to initialize core services:', error);
            setIsInitialized(true); // 仍然允许应用启动，但可能功能受限
        }
    }, []);

    if (!isInitialized) {
        return (
            <div style={{
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                height: '100vh',
                backgroundColor: '#0f172a',
                color: '#f8fafc'
            }}>
                <div>Initializing...</div>
            </div>
        );
    }

    return (
        <ThemeProvider>
            <LanguageProvider>
                <AppContent />
            </LanguageProvider>
        </ThemeProvider>
    );
}

export default App;
