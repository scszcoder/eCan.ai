import { HashRouter, Routes, Route } from 'react-router-dom';
import { ConfigProvider, theme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { routes, RouteConfig } from './routes';
import './styles/global.css';

// 配置 React Router future flags
const router = {
    future: {
        v7_startTransition: true,
        v7_relativeSplatPath: true
    }
};

// 自定义主题配置
const customTheme = {
    token: {
        colorPrimary: '#3b82f6',
        colorSuccess: '#22c55e',
        colorWarning: '#eab308',
        colorError: '#ef4444',
        colorInfo: '#0ea5e9',
        borderRadius: 8,
        wireframe: false,
    },
    algorithm: theme.darkAlgorithm,
    components: {
        Layout: {
            bodyBg: '#0f172a',
            headerBg: '#1e293b',
            siderBg: '#1e293b',
        },
        Menu: {
            darkItemBg: '#1e293b',
            darkItemSelectedBg: '#334155',
            darkItemHoverBg: '#334155',
        },
        Card: {
            colorBgContainer: '#1e293b',
            colorBorderSecondary: '#334155',
        },
        Button: {
            colorPrimary: '#3b82f6',
            colorPrimaryHover: '#2563eb',
        },
        Input: {
            colorBgContainer: '#334155',
            colorBorder: '#475569',
        },
        Table: {
            colorBgContainer: '#1e293b',
            headerBg: '#1e293b',
            headerColor: '#f8fafc',
            rowHoverBg: '#334155',
        },
    },
};

// 递归渲染路由
const renderRoutes = (routes: RouteConfig[]) => {
    return routes.map((route) => (
        <Route key={route.path} path={route.path} element={route.element}>
            {route.children && renderRoutes(route.children)}
        </Route>
    ));
};

function App() {
    return (
        <ConfigProvider
            locale={zhCN}
            theme={customTheme}
        >
            <HashRouter future={router.future}>
                <Routes>
                    {renderRoutes(routes)}
                </Routes>
            </HashRouter>
        </ConfigProvider>
    );
}

export default App;
