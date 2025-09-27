import React from 'react';
import { HashRouter, Routes, Route } from 'react-router-dom';
import { ConfigProvider, theme, App as AntdApp } from 'antd';
import { routes, RouteConfig } from './routes';
import { ThemeProvider, useTheme } from './contexts/ThemeContext';
import { LanguageProvider } from './contexts/LanguageContext';
import { getAntdLocale } from './i18n';
import { pageRefreshManager } from './services/events/PageRefreshManager';
import { logger, LogLevel } from './utils/logger';
import { antdTheme } from './styles/antdTheme';
import './styles/global.css';
import 'antd/dist/reset.css';
import './index.css';
import { set_ipc_api } from './services/ipc_api';
import { createIPCAPI } from './services/ipc';
import { IPCAPI } from './services/ipc';
import { protocolHandler } from './pages/Chat/utils/protocolHandler';
import { useToolStore } from './stores/toolStore';
import { useUserStore } from './stores/userStore';
import { logoutManager } from './services/LogoutManager';



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
    const { fetchTools } = useToolStore();
    const username = useUserStore((state) => state.username);

    // Note: avoid immediate fetch on username to prevent racing backend init; we poll readiness below

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
                    
                    // 清理工具状态
                    const toolStore = useToolStore.getState();
                    if (toolStore && typeof toolStore.clearTools === 'function') {
                        toolStore.clearTools();
                        logger.debug('[App] Tool state cleared');
                    }
                    
                    logger.info('[App] App cleanup completed');
                } catch (error) {
                    logger.error('[App] Error during cleanup:', error);
                }
            },
            priority: 30 // 较低优先级，在其他服务清理后执行
        });
    }, []);

    // Wait for backend to be fully ready before attempting to fetch tools schemas to avoid races
    React.useEffect(() => {
        if (!username) return;

        let cancelled = false;
        let timer: number | undefined;

        const pollReadyAndFetch = async () => {
            try {
                const api = IPCAPI.getInstance();
                const start = Date.now();
                const timeoutMs = 60_000; // 60s max wait
                const intervalMs = 1000; // 1s interval

                // quick check first
                const first = await api.getInitializationProgress();
                if (first.success && first.data?.fully_ready) {
                    if (!cancelled) {
                        await fetchTools(username);
                        // If still empty, force a backend refresh then refetch
                        try {
                            const toolsNow = (useToolStore as any).getState?.().tools || [];
                            if (!cancelled && (!Array.isArray(toolsNow) || toolsNow.length === 0)) {
                                console.warn('[App] Tools empty after ready; attempting backend refresh of tool schemas');
                                await api.refreshToolsSchemas();
                                if (!cancelled) await fetchTools(username);
                            }
                        } catch (e) {
                            console.warn('[App] Could not verify tools state or refresh schemas:', e);
                        }
                    }
                    return;
                }

                const tick = async (): Promise<void> => {
                    if (cancelled) return;
                    const resp = await api.getInitializationProgress();
                    if (resp.success && resp.data?.fully_ready) {
                        if (!cancelled) {
                            await fetchTools(username);
                            try {
                                const toolsNow = (useToolStore as any).getState?.().tools || [];
                                if (!cancelled && (!Array.isArray(toolsNow) || toolsNow.length === 0)) {
                                    console.warn('[App] Tools empty after ready; attempting backend refresh of tool schemas');
                                    await api.refreshToolsSchemas();
                                    if (!cancelled) await fetchTools(username);
                                }
                            } catch (e) {
                                console.warn('[App] Could not verify tools state or refresh schemas:', e);
                            }
                        }
                        return;
                    }
                    if (Date.now() - start > timeoutMs) {
                        console.warn('[App] Backend not fully ready within timeout; proceeding to fetch tools anyway');
                        if (!cancelled) await fetchTools(username);
                        return;
                    }
                    timer = window.setTimeout(() => { tick().catch(console.error); }, intervalMs);
                };

                timer = window.setTimeout(() => { tick().catch(console.error); }, intervalMs);
            } catch (e) {
                console.error('[App] Error polling initialization progress:', e);
                // best effort fetch
                if (!cancelled) fetchTools(username).catch(console.error);
            }
        };

        pollReadyAndFetch().catch(console.error);

        return () => {
            cancelled = true;
            if (timer) {
                window.clearTimeout(timer);
                timer = null;
            }
        };
    }, [username, fetchTools]);

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
            // 初始化 IPC 服务（同步）
            set_ipc_api(createIPCAPI());

            // 异步初始化其他服务
            const initOtherServices = async () => {
                try {
                    // 初始化页面刷新管理器
                    pageRefreshManager.initialize();

                    // 初始化协议处理器
                    protocolHandler.init();

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
