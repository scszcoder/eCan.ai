import React, { Suspense } from 'react';
import { Navigate } from 'react-router-dom';
import MainLayout from '../components/Layout/MainLayout';
import { Spin } from 'antd';
import { userStorageManager } from '../services/storage/UserStorageManager';
import AgentsRouteWrapper from './AgentsRouteWrapper';
import MainRouteWrapper from './MainRouteWrapper';

// PageComponent懒Load
const Login = React.lazy(() => import('../pages/Login/index'));
const Dashboard = React.lazy(() => import('../pages/Dashboard/Dashboard'));
const Vehicles = React.lazy(() => import('../pages/Vehicles/Vehicles'));
const Schedule = React.lazy(() => import('../pages/Schedule/Schedule'));
const Chat = React.lazy(() => import('../pages/Chat/index'));
const Skills = React.lazy(() => import('../pages/Skills/Skills'));
const SkillEditor = React.lazy(() => import('../pages/SkillEditor/SkillEditor'));
const Analytics = React.lazy(() => import('../pages/Analytics/Analytics'));
const Tasks = React.lazy(() => import('../pages/Tasks/Tasks'));
const Tools = React.lazy(() => import('../pages/Tools/Tools'));
const Settings = React.lazy(() => import('../pages/Settings/Settings'));
const Console = React.lazy(() => import('../pages/Console/Console'));
const KnowledgePorted = React.lazy(() => import('../pages/Knowledge/LightRAGPorted'));
const Tests = React.lazy(() => import('../pages/Tests/Tests'));
const OrgNavigator = React.lazy(() => import('../pages/Agents/OrgNavigator'));
const AgentDetails = React.lazy(() => import('../pages/Agents/components/AgentDetails'));
const Orgs = React.lazy(() => import('../pages/Orgs/Orgs'));
const Warehouses = React.lazy(() => import('../pages/Warehouses/Warehouses'));
const Products = React.lazy(() => import('../pages/Products/Products'));
const Prompts = React.lazy(() => import('../pages/Prompts/Prompts'));
const Account = React.lazy(() => import('../pages/Account/Account'));
const ShippingLabel = React.lazy(() => import('../pages/ShippingLabel/ShippingLabel'));

// LoadComponent包装器
const LazyWrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => (
    <Suspense fallback={
        <div style={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            height: '200px',
            background: 'var(--bg-primary, #0f172a)'
        }}>
            <Spin size="large" />
        </div>
    }>
        {children}
    </Suspense>
);

// 路由ConfigurationType
export interface RouteConfig {
    path: string;
    element: React.ReactNode;
    children?: RouteConfig[];
    auth?: boolean;
    keepAlive?: boolean; // 是否EnabledPage持久化
}

// Check认证Status
export const isAuthenticated = () => {
    return userStorageManager.isAuthenticated();
};

// 受保护的路由Component
export const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    if (!isAuthenticated()) {
        return <Navigate to="/login" replace />;
    }
    return <MainLayout>{children}</MainLayout>;
};

// 登录路由组件 - 如果已登录则重定向
const LoginRoute: React.FC = () => {
    if (isAuthenticated()) {
        return <Navigate to="/" replace />;
    }
    return <LazyWrapper><Login /></LazyWrapper>;
};

// Public路由
export const publicRoutes: RouteConfig[] = [
    {
        path: '/login',
        element: <LoginRoute />,
    },
];

// 受保护的路由
export const protectedRoutes: RouteConfig[] = [
    {
        path: '/',
        element: <ProtectedRoute><MainRouteWrapper /></ProtectedRoute>,
        children: [
            {
                path: '',
                element: <Navigate to="/agents" replace />,
            },
            {
                path: 'dashboard',
                element: <LazyWrapper><Dashboard /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'vehicles',
                element: <LazyWrapper><Vehicles /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'schedule',
                element: <LazyWrapper><Schedule /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'chat',
                element: <LazyWrapper><Chat /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'skills',
                element: <LazyWrapper><Skills /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'skill_editor',
                element: <LazyWrapper><SkillEditor /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'agents',
                element: <AgentsRouteWrapper />,
                children: [
                    {
                        path: '',
                        element: <LazyWrapper><OrgNavigator /></LazyWrapper>,
                        keepAlive: true,
                    },
                    {
                        path: 'details/:id',
                        element: <LazyWrapper><AgentDetails /></LazyWrapper>,
                        keepAlive: false, // Details页不Need保活，每次都重新Load
                    },
                    {
                        path: 'add',
                        element: <LazyWrapper><AgentDetails /></LazyWrapper>,
                        keepAlive: false, // Add页不Need保活
                    },
                    {
                        path: 'organization/:orgId/*',
                        element: <LazyWrapper><OrgNavigator /></LazyWrapper>,
                        keepAlive: true,
                        // Note：All organization Path共享同一个Cache实例（通过 AgentsRouteWrapper Implementation）
                        // 这样在不同组织间Toggle时，OrgNavigator 会保持Status
                    },
                ],
            },
            {
                path: 'analytics',
                element: <LazyWrapper><Analytics /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'tasks',
                element: <LazyWrapper><Tasks /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'tools',
                element: <LazyWrapper><Tools /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'warehouses',
                element: <LazyWrapper><Warehouses /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'products',
                element: <LazyWrapper><Products /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'prompts',
                element: <LazyWrapper><Prompts /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'account',
                element: <LazyWrapper><Account /></LazyWrapper>,
                keepAlive: false,
            },
            {
                path: 'settings',
                element: <LazyWrapper><Settings /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'console',
                element: <LazyWrapper><Console /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'knowledge-ported',
                element: <LazyWrapper><KnowledgePorted /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'tests',
                element: <LazyWrapper><Tests /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'orgs',
                element: <LazyWrapper><Orgs /></LazyWrapper>,
                keepAlive: true,
            },
            {
                path: 'shipping-label',
                element: <LazyWrapper><ShippingLabel /></LazyWrapper>,
                keepAlive: true,
            },
        ],
    },
];

// 404路由
export const notFoundRoute: RouteConfig = {
    path: '*',
    element: <Navigate to="/" replace />,
};

// All路由
export const routes: RouteConfig[] = [
    ...publicRoutes,
    ...protectedRoutes,
    notFoundRoute,
];

// MenuConfiguration
export const menuItems = [
    {
        key: '/dashboard',
        icon: 'DashboardOutlined',
        label: 'menu.dashboard',
    },
    {
        key: '/vehicles',
        icon: 'ClusterOutlined',
        label: 'menu.vehicles',
    },
    {
        key: '/schedule',
        icon: 'CalendarOutlined',
        label: 'menu.schedule',
    },
    {
        key: '/chat',
        icon: 'MessageOutlined',
        label: 'menu.chat',
    },
    {
        key: '/skills',
        icon: 'RobotOutlined',
        label: 'menu.skills',
    },
    {
        key: '/skill_editor',
        icon: 'EditOutlined',
        label: 'menu.skill_editor',
    },
    {
        key: '/agents',
        icon: 'TeamOutlined',
        label: 'menu.agents',
    },
    {
        key: '/analytics',
        icon: 'BarChartOutlined',
        label: 'menu.analytics',
    },
    {
        key: '/tasks',
        icon: 'OrderedListOutlined',
        label: 'menu.tasks',
    },
    {
        key: '/tools',
        icon: 'ToolOutlined',
        label: 'menu.tools',
    },
    {
        key: '/settings',
        icon: 'SettingOutlined',
        label: 'menu.settings',
    },
    {
        key: '/console',
        icon: 'SettingOutlined',
        label: 'menu.console',
    },
    {
        key: '/tests',
        icon: 'ExperimentOutlined',
        label: 'menu.tests',
    },
    {
        key: '/shipping-label',
        icon: 'PrinterOutlined',
        label: 'menu.shipping_label',
    },
]; 
