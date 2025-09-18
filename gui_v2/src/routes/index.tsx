import React, { Suspense } from 'react';
import { Navigate, Outlet } from 'react-router-dom';
import MainLayout from '../components/Layout/MainLayout';
import { Spin } from 'antd';
import { userStorageManager } from '../services/storage/UserStorageManager';

// 页面组件懒加载
const Login = React.lazy(() => import('../pages/Login/index'));
const Dashboard = React.lazy(() => import('../pages/Dashboard/Dashboard'));
const Vehicles = React.lazy(() => import('../pages/Vehicles/Vehicles'));
const Schedule = React.lazy(() => import('../pages/Schedule/Schedule'));
const Chat = React.lazy(() => import('../pages/Chat/index'));
const Skills = React.lazy(() => import('../pages/Skills/Skills'));
const SkillEditor = React.lazy(() => import('../pages/SkillEditor/SkillEditor'));
const Agents = React.lazy(() => import('../pages/Agents/Agents'));
const Analytics = React.lazy(() => import('../pages/Analytics/Analytics'));
const Tasks = React.lazy(() => import('../pages/Tasks/Tasks'));
const Tools = React.lazy(() => import('../pages/Tools/Tools'));
const Settings = React.lazy(() => import('../pages/Settings/Settings'));
const Console = React.lazy(() => import('../pages/Console/Console'));
const KnowledgePlatform = React.lazy(() => import('../pages/Knowledge/index'));
const Tests = React.lazy(() => import('../pages/Tests/Tests'));
const VirtualPlatform = React.lazy(() => import('../pages/Agents/VirtualPlatform'));
const DepartmentRoom = React.lazy(() => import('../pages/Agents/DepartmentRoom'));
const AgentDetails = React.lazy(() => import('../pages/Agents/components/AgentDetails'));

// Agents 路由包装器，用于防止不必要的重新渲染
const AgentsRouteWrapper: React.FC = () => {
    return React.useMemo(() => <LazyWrapper><Agents /></LazyWrapper>, []);
};

// 加载组件包装器
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

// 路由配置类型
export interface RouteConfig {
    path: string;
    element: React.ReactNode;
    children?: RouteConfig[];
    auth?: boolean;
}

// 检查认证状态
export const isAuthenticated = () => {
    return userStorageManager.isAuthenticated();
};

// 受保护的路由组件
export const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    if (!isAuthenticated()) {
        return <Navigate to="/login" replace />;
    }
    return <MainLayout>{children}</MainLayout>;
};

// 公共路由
export const publicRoutes: RouteConfig[] = [
    {
        path: '/login',
        element: isAuthenticated() ? <Navigate to="/" replace /> : <LazyWrapper><Login /></LazyWrapper>,
    },
];

// 受保护的路由
export const protectedRoutes: RouteConfig[] = [
    {
        path: '/',
        element: <ProtectedRoute><Outlet /></ProtectedRoute>,
        children: [
            {
                path: '',
                element: <Navigate to="/agents" replace />,
            },
            {
                path: 'dashboard',
                element: <LazyWrapper><Dashboard /></LazyWrapper>,
            },
            {
                path: 'vehicles',
                element: <LazyWrapper><Vehicles /></LazyWrapper>,
            },
            {
                path: 'schedule',
                element: <LazyWrapper><Schedule /></LazyWrapper>,
            },
            {
                path: 'chat',
                element: <LazyWrapper><Chat /></LazyWrapper>,
            },
            {
                path: 'skills',
                element: <LazyWrapper><Skills /></LazyWrapper>,
            },
            {
                path: 'skill_editor',
                element: <LazyWrapper><SkillEditor /></LazyWrapper>,
            },
            {
                path: 'agents',
                element: <AgentsRouteWrapper />,
                children: [
                    {
                        path: '',
                        element: <LazyWrapper><VirtualPlatform /></LazyWrapper>,
                    },
                    {
                        path: 'details/:id',
                        element: <LazyWrapper><AgentDetails /></LazyWrapper>,
                    },
                    {
                        path: 'room/:departmentId',
                        element: <LazyWrapper><DepartmentRoom /></LazyWrapper>,
                    },
                ],
            },
            {
                path: 'analytics',
                element: <LazyWrapper><Analytics /></LazyWrapper>,
            },
            {
                path: 'tasks',
                element: <LazyWrapper><Tasks /></LazyWrapper>,
            },
            {
                path: 'tools',
                element: <LazyWrapper><Tools /></LazyWrapper>,
            },
            {
                path: 'settings',
                element: <LazyWrapper><Settings /></LazyWrapper>,
            },
            {
                path: 'console',
                element: <LazyWrapper><Console /></LazyWrapper>,
            },
            {
                path: 'knowledge',
                element: <LazyWrapper><KnowledgePlatform /></LazyWrapper>,
            },
            {
                path: 'tests',
                element: <LazyWrapper><Tests /></LazyWrapper>,
            },
        ],
    },
];

// 404路由
export const notFoundRoute: RouteConfig = {
    path: '*',
    element: <Navigate to="/" replace />,
};

// 所有路由
export const routes: RouteConfig[] = [
    ...publicRoutes,
    ...protectedRoutes,
    notFoundRoute,
];

// 菜单配置
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
        key: '/knowledge',
        icon: 'ReadOutlined',
        label: 'menu.knowledge',
    },
    {
        key: '/tests',
        icon: 'ExperimentOutlined',
        label: 'menu.tests',
    },
]; 