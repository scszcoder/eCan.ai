import React, { useMemo } from 'react';
import { useLocation } from 'react-router-dom';
import KeepAliveRouteOutlet from 'keepalive-for-react-router';

/**
 * 主路由包装器
 * 
 * 为AllPage提供智能的 KeepAlive Cache key 管理
 * 
 * Cache策略：
 * 1. Chat Page：忽略 URL Parameter（agentId），使用固定 key '/chat'
 * 2. 其他Page：使用完整Path（pathname + search）
 * 
 * 这样Can确保：
 * - Chat Page在Toggle agent Filter器时保持Status
 * - 其他Page的 URL Parameter变化时会Create新的Cache（IfNeed）
 */
const MainRouteWrapper: React.FC = () => {
    const location = useLocation();
    // ⚠️ 关键Optimize：提取字符串，避免 location 对象Reference变化导致重复Render
    const pathname = location.pathname;
    const search = location.search;
    
    // 计算When前路由的 cache key
    const activeCacheKey = useMemo(() => {
        // Chat Page：忽略 URL Parameter，使用固定的 cache key
        if (pathname === '/chat') {
            return '/chat';
        }
        // Agents Page：All /agents 相关Path共享同一个 cache key
        // 包括 /agents, /agents/organization/*, /agents/details/*, /agents/add
        if (pathname === '/agents' || pathname.startsWith('/agents/')) {
            return '/agents';
        }
        // 其他Page：使用完整Path（pathname + search）
        return pathname + search;
    }, [pathname, search]); // ⚠️ 只Dependency字符串，不Dependency location 对象
    
    return <KeepAliveRouteOutlet activeCacheKey={activeCacheKey} />;
};

export default MainRouteWrapper;
