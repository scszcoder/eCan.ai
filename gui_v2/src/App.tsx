import { HashRouter, Routes, Route } from 'react-router-dom';
import { ConfigProvider, theme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import enUS from 'antd/locale/en_US';
import { routes, RouteConfig } from './routes';
import { ThemeProvider, useTheme } from './contexts/ThemeContext';
import { LanguageProvider } from './contexts/LanguageContext';
import { useTranslation } from 'react-i18next';
import './styles/global.css';

// 配置 React Router future flags
const router = {
    future: {
        v7_startTransition: true,
        v7_relativeSplatPath: true
    }
};

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
    const { i18n } = useTranslation();
    const isDark = currentTheme === 'dark' || (currentTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
    const locale = i18n.language === 'en-US' ? enUS : zhCN;

    return (
        <ConfigProvider
            locale={locale}
            theme={getThemeConfig(isDark)}
        >
            <HashRouter future={router.future}>
                <Routes>
                    {renderRoutes(routes)}
                </Routes>
            </HashRouter>
        </ConfigProvider>
    );
};

function App() {
    return (
        <ThemeProvider>
            <LanguageProvider>
                <AppContent />
            </LanguageProvider>
        </ThemeProvider>
    );
}

export default App;
