import React from 'react';
import { Outlet } from 'react-router-dom';

/**
 * Agents 路由包装器
 * 
 * 使用普通 Outlet，缓存由 MainRouteWrapper 统一管理
 * 所有 /agents/* 路径共享同一个缓存实例
 */
const AgentsRouteWrapper: React.FC = () => {
    return <Outlet />;
};

export default AgentsRouteWrapper;
