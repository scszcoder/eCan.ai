import React from 'react';
import { Navigate } from 'react-router-dom';
import MainLayout from '../components/Layout/MainLayout';
import Login from '../pages/Login';
import Dashboard from '../pages/Dashboard';
import Vehicles from '../pages/Vehicles';
import Schedule from '../pages/Schedule';
import Chat from '../pages/Chat';
import Skills from '../pages/Skills';
import Agents from '../pages/Agents';
import Analytics from '../pages/Analytics';
import Apps from '../pages/Apps';
import Tools from '../pages/Tools';
import Settings from '../pages/Settings';

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
        element: <ProtectedRoute><Dashboard /></ProtectedRoute>,
    },
    {
        path: '/vehicles',
        element: <ProtectedRoute><Vehicles /></ProtectedRoute>,
    },
    {
        path: '/schedule',
        element: <ProtectedRoute><Schedule /></ProtectedRoute>,
    },
    {
        path: '/chat',
        element: <ProtectedRoute><Chat /></ProtectedRoute>,
    },
    {
        path: '/skills',
        element: <ProtectedRoute><Skills /></ProtectedRoute>,
    },
    {
        path: '/agents',
        element: <ProtectedRoute><Agents /></ProtectedRoute>,
    },
    {
        path: '/analytics',
        element: <ProtectedRoute><Analytics /></ProtectedRoute>,
    },
    {
        path: '/apps',
        element: <ProtectedRoute><Apps /></ProtectedRoute>,
    },
    {
        path: '/tools',
        element: <ProtectedRoute><Tools /></ProtectedRoute>,
    },
    {
        path: '/settings',
        element: <ProtectedRoute><Settings /></ProtectedRoute>,
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