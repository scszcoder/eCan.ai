import React, { useMemo } from 'react';
import { useLocation, useOutlet } from 'react-router-dom';
import { KeepAlive } from 'keepalive-for-react';

/**
 * 主路由包装器 - 管理 KeepAlive 缓存策略
 * 
 * 缓存策略：
 * - /chat → 固定 key '/chat'
 * - /agents/* → 固定 key '/agents'（内部由 AgentsRouteWrapper 管理子路由缓存）
 * - /knowledge-ported → 固定 key '/knowledge-ported'
 * - 其他 → pathname + search
 */
const MainRouteWrapper: React.FC = () => {
    const location = useLocation();
    const pathname = location.pathname;
    const search = location.search;
    const outlet = useOutlet();
    
    const activeCacheKey = useMemo(() => {
        if (pathname === '/chat') {
            return '/chat';
        }
        // Skills/Tasks should keep UI state even when query params change (e.g. taskId deep links)
        if (pathname === '/skills') {
            return '/skills';
        }
        if (pathname === '/tasks') {
            return '/tasks';
        }
        // Knowledge page should keep all tabs state (documents, retrieval, settings, graph)
        if (pathname === '/knowledge-ported') {
            return '/knowledge-ported';
        }
        // 所有 /agents/* 路径使用同一个 cache key
        // AgentsRouteWrapper 会进一步管理子路由的缓存
        if (pathname === '/agents' || pathname.startsWith('/agents/')) {
            return '/agents';
        }
        return pathname + search;
    }, [pathname, search]);
    
    return (
        <KeepAlive 
            activeCacheKey={activeCacheKey}
            max={20}
        >
            {outlet}
        </KeepAlive>
    );
};

export default MainRouteWrapper;
