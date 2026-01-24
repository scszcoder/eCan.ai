import React from 'react';
import { BrowserRouter, HashRouter, Routes, Route } from 'react-router-dom';
import { ConfigProvider, theme, App as AntdApp } from 'antd';
import { registerOnboardingModalApi } from './services/onboarding/onboardingService';
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
import { createIPCAPI } from './services/ipc/api';
import { ipcClient } from './services/ipc/ipcClient';
import { protocolHandler } from './pages/Chat/utils/protocolHandler';
import { useUserStore } from './stores/userStore';
import { useAgentStore } from './stores/agentStore';
import { logoutManager } from './services/LogoutManager';
import { initializePlatform } from './config/platform';
import { initializeStoreSync, cleanupStoreSync } from './services/storeSync';
import { orgDataSyncService } from './services/OrgDataSyncService';
import { isWebPlatform } from './config/platform';
import { webAuthSession } from './services/auth/webAuthSession';
import { tokenRefreshService } from './services/auth/tokenRefreshService';
import { startWebSubscriptions } from './services/web/appSyncSubscriptions';
import './utils/videoSupport'; // Initialize video support check on page load

const getEnv = () => (typeof import.meta !== 'undefined' && (import.meta as any).env ? (import.meta as any).env : {});

const isTruthyEnvValue = (value: unknown): boolean => {
    const normalized = String(value ?? '').trim().toLowerCase();
    return normalized === '1' || normalized === 'true' || normalized === 'yes' || normalized === 'on';
};



// Configure React Router future flags
// const router = {
//     future: {
//         v7_startTransition: true,
//         v7_relativeSplatPath: true
//     }
// };

// Custom theme configuration - Standard Ant Design Architecture
const getThemeConfig = (isDark: boolean) => ({
    token: {
        // Brand colors
        colorPrimary: '#3b82f6',
        colorSuccess: '#22c55e',
        colorWarning: '#eab308',
        colorError: '#ef4444',
        colorInfo: '#0ea5e9',
        borderRadius: 8,
        wireframe: false,
        // Explicitly set background colors using original color scheme
        ...(isDark ? {
            colorBgLayout: '#0f172a',      // Deep blue-black page background (original color)
            colorBgContainer: '#1e293b',   // Deep blue-gray container background (original color)
            colorBgElevated: '#1e293b',    // Deep blue-gray elevated background
        } : {
            colorBgLayout: '#f0f2f5',      // Light gray page background
            colorBgContainer: '#ffffff',   // White container background
            colorBgElevated: '#ffffff',    // White elevated background
        }),
    },
    algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
    components: {
        Layout: {
            // Layout component background colors using original color scheme
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

// Recursively render routes
const renderRoutes = (routes: RouteConfig[]) => {
    return routes.map((route) => (
        <Route key={route.path} path={route.path} element={route.element}>
            {route.children && renderRoutes(route.children)}
        </Route>
    ));
};

const AppContent = () => {
    const ModalRegistrar: React.FC = () => {
        const api = AntdApp.useApp();
        React.useEffect(() => {
            try {
                if (api && (api as any).modal) {
                    registerOnboardingModalApi((api as any).modal);
                }
            } catch {}
            return () => registerOnboardingModalApi(null);
        }, [api]);
        return null;
    };
    // Initialize platform at app mount so IPC gating flags are correct
    React.useEffect(() => {
        try {
            initializePlatform();
        } catch (e) {
            // eslint-disable-next-line no-console
            console.warn('[App] Failed to initialize platform, defaulting to env-based config:', e);
        }

        try {
            const env = getEnv();
            const detectedMode = ipcClient.getMode?.() ?? null;
            const platform = detectedMode || (isWebPlatform() ? 'web' : 'desktop');
            const forceIpcMode = platform === 'desktop' && isTruthyEnvValue(env.VITE_IPC_MODE);
            logger.info('[App] Platform/IPC mode', {
                platform,
                VITE_IPC_MODE: env.VITE_IPC_MODE,
                forceIpcMode,
            });
        } catch (e) {
            logger.debug('[App] Failed to log platform/IPC mode', e);
        }
    }, []);

    const { theme: currentTheme } = useTheme();
    const isDark = currentTheme === 'dark' || (currentTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);

    // Apply global background color to body and #root
    React.useEffect(() => {
        const bgColor = isDark ? '#0f172a' : '#f0f2f5';  // Restore original deep blue-black color
        const textColor = isDark ? '#f8fafc' : '#000000';
        
        document.body.style.backgroundColor = bgColor;
        document.body.style.color = textColor;
        
        const root = document.getElementById('root');
        if (root) {
            root.style.backgroundColor = bgColor;
        }
    }, [isDark]);

    // Note: avoid immediate fetch on username to prevent racing backend init; we poll readiness below

    // Initialize organization data sync service (background listeners)
    React.useEffect(() => {
        orgDataSyncService.initialize();
        
        return () => {
            orgDataSyncService.cleanup();
        };
    }, []);

    React.useEffect(() => {
        if (!isWebPlatform()) return;
        const session = webAuthSession.getSession();
        if (session?.accessToken) {
            tokenRefreshService.start(session.accessToken, {
                checkInterval: 10 * 60 * 1000,
                refreshThreshold: 10 * 60,
            });
        }
    }, []);

    React.useEffect(() => {
        const env = getEnv();
        const forceIpcMode = !isWebPlatform() && isTruthyEnvValue(env.VITE_IPC_MODE);
        if (forceIpcMode) return;

        const cleanup = startWebSubscriptions();
        return () => cleanup?.();
    }, []);

    // Register App-level cleanup for logout
    React.useEffect(() => {
        logoutManager.registerCleanup({
            name: 'App',
            cleanup: () => {
                try {
                    logger.info('[App] Cleaning up for logout...');

                    // Clean up user state
                    const userStore = useUserStore.getState();
                    if (userStore && typeof userStore.setUsername === 'function') {
                        userStore.setUsername(null);
                        logger.debug('[App] User state cleared');
                    }

                    // Clean up agents state
                    const agentStore = useAgentStore.getState();
                    if (agentStore && typeof agentStore.setAgents === 'function') {
                        agentStore.setAgents([]);
                        logger.debug('[App] Agent state cleared');
                    }

                    // Tool state cleanup has been moved to Tools page for on-demand processing
                    
                    // Clean up store sync listeners
                    cleanupStoreSync();
                    logger.debug('[App] Store sync listeners cleaned up');

                    // Clean up organization data sync service
                    orgDataSyncService.cleanup();
                    logger.debug('[App] Org data sync service cleaned up');

                    logger.info('[App] App cleanup completed');
                } catch (error) {
                    logger.error('[App] Error during cleanup:', error);
                }
            },
            priority: 30 // Lower priority, execute after other services cleanup
        });
    }, []);

    // Tools are now loaded on-demand when accessing Tools page or skill editor
    // This improves startup performance by removing unnecessary preloading

    // Use Vite's BASE_URL which respects the 'base' config in vite.config.ts
    // In dev: BASE_URL = '/', in production: BASE_URL = './' (or custom VITE_BASE)
    // For file:// protocol (PyInstaller), use HashRouter to avoid History API SecurityError
    const isFileProtocol = window.location.protocol === 'file:';
    const basename = isFileProtocol ? '/' : (import.meta.env.BASE_URL.replace(/\/$/, '') || '/');
    
    // Use HashRouter for file:// protocol, BrowserRouter for http/https
    const Router = isFileProtocol ? HashRouter : BrowserRouter;
    const routerProps = isFileProtocol ? {} : { basename };

    return (
        <ConfigProvider
            locale={getAntdLocale()}
            theme={getThemeConfig(isDark)}
        >
            <AntdApp>
                <ModalRegistrar />
                <Router {...routerProps}>
                    <Routes>
                        {renderRoutes(routes)}
                    </Routes>
                </Router>
            </AntdApp>
        </ConfigProvider>
    );
};

function App() {
    const [isInitialized, setIsInitialized] = React.useState(false);

    React.useEffect(() => {
        const initApp = async () => {
            try {
                // Initialize IPC service (supports desktop + web)
                await ipcClient.initialize();
                set_ipc_api(createIPCAPI());

                // Initialize platform configuration (synchronous) - depends on IPC API for platform detection
                initializePlatform();

                // Asynchronously initialize other services
                const initOtherServices = async () => {
                    try {
                        // Initialize page refresh manager
                        pageRefreshManager.initialize();

                        // Initialize protocol handler
                        protocolHandler.init();
                        
                        // Initialize store sync listeners
                        initializeStoreSync();

                        // Set log level based on environment
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
                setIsInitialized(true); // Still allow app to start, but functionality may be limited
            }
        };

        void initApp();
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
