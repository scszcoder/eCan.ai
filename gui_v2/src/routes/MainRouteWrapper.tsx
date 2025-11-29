import React, { useMemo } from 'react';
import { useLocation } from 'react-router-dom';
import KeepAliveRouteOutlet from 'keepalive-for-react-router';

/**
 * 主路由包装器 - 管理 KeepAlive 缓存策略
 * 
 * 缓存策略：
 * - /chat → 固定 key '/chat'
 * - /agents/* → 固定 key '/agents'（内部由 AgentsRouteWrapper 管理子路由缓存）
 * - 其他 → pathname + search
 */
const MainRouteWrapper: React.FC = () => {
    const location = useLocation();
    const pathname = location.pathname;
    const search = location.search;
    
    const activeCacheKey = useMemo(() => {
        if (pathname === '/chat') {
            return '/chat';
        }
        // 所有 /agents/* 路径使用同一个 cache key
        // AgentsRouteWrapper 会进一步管理子路由的缓存
        if (pathname === '/agents' || pathname.startsWith('/agents/')) {
            return '/agents';
        }
        return pathname + search;
    }, [pathname, search]);
    
    return <KeepAliveRouteOutlet activeCacheKey={activeCacheKey} />;
};

export default MainRouteWrapper;
