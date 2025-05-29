import React from 'react';
import { Navigate, Outlet } from 'react-router-dom';
import MainLayout from '../components/Layout/MainLayout';
import Login from '../pages/Login';
import Dashboard from '../pages/Dashboard';
import Vehicles from '../pages/Vehicles';
import Schedule from '../pages/Schedule';
import Chat from '../pages/Chat';
import Skills from '../pages/Skills';
import SkillEditor from '../pages/SkillEditor';
import Agents from '../pages/Agents';
import Analytics from '../pages/Analytics';
import Apps from '../pages/Apps';
import Tasks from '../pages/Tasks';
import Tools from '../pages/Tools';
import Settings from '../pages/Settings';
import Console from '../pages/Console';

// 路由配置类型
export interface RouteConfig {
    path: string;
    element: React.ReactNode;
    children?: RouteConfig[];
    auth?: boolean;
}

// 检查认证状态
export const isAuthenticated = () => {
    return localStorage.getItem('isAuthenticated') === 'true';
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
        element: isAuthenticated() ? <Navigate to="/" replace /> : <Login />,
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
                element: <Navigate to="/dashboard" replace />,
            },
            {
                path: 'dashboard',
                element: <Dashboard />,
            },
            {
                path: 'vehicles',
                element: <Vehicles />,
            },
            {
                path: 'schedule',
                element: <Schedule />,
            },
            {
                path: 'chat',
                element: <Chat />,
            },
            {
                path: 'skills',
                element: <Skills />,
            },
            {
                path: 'skill_editor',
                element: <SkillEditor />,
            },
            {
                path: 'agents',
                element: <Agents />,
            },
            {
                path: 'analytics',
                element: <Analytics />,
            },
            {
                path: 'apps',
                element: <Apps />,
            },
            {
                path: 'tasks',
                element: <Tasks />,
            },
            {
                path: 'tools',
                element: <Tools />,
            },
            {
                path: 'settings',
                element: <Settings />,
            },
            {
                path: 'console',
                element: <Console />,
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
        key: '/apps',
        icon: 'AppstoreOutlined',
        label: 'menu.apps',
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
]; 