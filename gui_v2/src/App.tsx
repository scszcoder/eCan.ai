import React from 'react';
import { BrowserRouter, HashRouter, Routes, Route } from 'react-router-dom';
import { ConfigProvider, App as AntdApp } from 'antd';
import { registerOnboardingModalApi } from './services/onboarding/onboardingService';
import { routes, RouteConfig } from './routes';
import { ThemeProvider, useTheme } from './contexts/ThemeContext';
import { LanguageProvider } from './contexts/LanguageContext';
import { AppConfigProvider } from './contexts/AppConfigContext';
import { getAntdLocale } from './i18n';
import { pageRefreshManager } from './services/events/PageRefreshManager';
import { logger, LogLevel } from './utils/logger';
import './styles/global.css';
import { getAntdThemeConfig } from './styles/antdTheme';
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
import { GlobalAgentChat } from './components/GlobalAgentChat';
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

// antd theme is derived from the shared design tokens in styles/antdTheme.ts,
// so the TS token values and the CSS custom properties in global.css stay in
// sync. Do not restate colours here — add them to antdTheme.ts instead.

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
            const detectedMode = (ipcClient as any).getMode?.() ?? null;
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

    // Let the design tokens own the page background. The theme contract keeps
    // every colour in global.css (`:root` = dark, `body.light` = light); this
    // effect used to hardcode `#f0f2f5` for light, which silently overrode
    // `--bg-primary` and left cards only 1.045:1 apart from the page behind
    // them. Reading the token keeps one source of truth.
    React.useEffect(() => {
        const styles = getComputedStyle(document.body);
        const bgColor = styles.getPropertyValue('--bg-primary').trim()
            || (isDark ? '#0f172a' : '#eef2f7');
        const textColor = styles.getPropertyValue('--text-primary').trim()
            || (isDark ? '#f8fafc' : '#0f172a');

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
    const hasHashRoute = typeof window !== 'undefined' && window.location.hash.startsWith('#/');
    const rawBase = import.meta.env.BASE_URL;
    const normalizedBase = rawBase.startsWith('./') ? '/' : rawBase;
    const basename = isFileProtocol ? '/' : (normalizedBase.replace(/\/$/, '') || '/');
    
    // Use HashRouter for file:// protocol or when hash routing is present
    const Router = (isFileProtocol || hasHashRoute) ? HashRouter : BrowserRouter;
    const routerProps = (isFileProtocol || hasHashRoute) ? {} : { basename };

    // Block rendering until AppConfig is loaded to prevent flash of wrong region content
    // Note: We used to block here with LoadingProgress, but that caused an extra
    // loading screen after splash. Now we let children render even during config load
    // - Login page handles missing config gracefully (shows LoginCN/LoginIntl based on default)
    // - Protected routes will redirect to login anyway if config not ready

    return (
        <ConfigProvider
            locale={getAntdLocale()}
            theme={getAntdThemeConfig(isDark)}
        >
            <AntdApp>
                <ModalRegistrar />
                <Router {...routerProps}>
                    <div style={{ display: 'flex', width: '100vw', height: '100vh', minHeight: 0 }}>
                        <div style={{ flex: 1, minWidth: 0, height: '100%', position: 'relative' }}>
                            <Routes>
                                {renderRoutes(routes)}
                            </Routes>
                        </div>
                        <GlobalAgentChat />
                    </div>
                </Router>
            </AntdApp>
        </ConfigProvider>
    );
};

function App() {
    // Initialize services in background (non-blocking)
    React.useEffect(() => {
        const initApp = async () => {
            try {
                await ipcClient.initialize();
                set_ipc_api(createIPCAPI());
                initializePlatform();

                // Initialize other services (non-blocking)
                pageRefreshManager.initialize();
                protocolHandler.init();
                initializeStoreSync();

                const isDevelopment = process.env.NODE_ENV === 'development';
                if (isDevelopment) {
                    logger.setLevel(LogLevel.DEBUG);
                } else {
                    logger.setLevel(LogLevel.INFO);
                }
            } catch (error) {
                console.error('[App] Initialization error:', error);
            }
        };

        void initApp();
    }, []);

    return (
        <ThemeProvider>
            <LanguageProvider>
                <AppConfigProvider>
                    <AppContent />
                </AppConfigProvider>
            </LanguageProvider>
        </ThemeProvider>
    );
}

export default App;
