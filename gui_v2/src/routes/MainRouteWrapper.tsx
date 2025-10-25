import React, { useMemo } from 'react';
import { useLocation } from 'react-router-dom';
import KeepAliveRouteOutlet from 'keepalive-for-react-router';

/**
 * 主路由包装器
 * 
 * 为所有页面提供智能的 KeepAlive 缓存 key 管理
 * 
 * 缓存策略：
 * 1. Chat 页面：忽略 URL 参数（agentId），使用固定 key '/chat'
 * 2. 其他页面：使用完整路径（pathname + search）
 * 
 * 这样可以确保：
 * - Chat 页面在切换 agent 过滤器时保持状态
 * - 其他页面的 URL 参数变化时会创建新的缓存（如果需要）
 */
const MainRouteWrapper: React.FC = () => {
    const location = useLocation();
    // ⚠️ 关键优化：提取字符串，避免 location 对象引用变化导致重复渲染
    const pathname = location.pathname;
    const search = location.search;
    
    // 计算当前路由的 cache key
    const activeCacheKey = useMemo(() => {
        // Chat 页面：忽略 URL 参数，使用固定的 cache key
        if (pathname === '/chat') {
            return '/chat';
        }
        // Agents 页面：所有 /agents 相关路径共享同一个 cache key
        // 包括 /agents, /agents/organization/*, /agents/details/*, /agents/add
        if (pathname === '/agents' || pathname.startsWith('/agents/')) {
            return '/agents';
        }
        // 其他页面：使用完整路径（pathname + search）
        return pathname + search;
    }, [pathname, search]); // ⚠️ 只依赖字符串，不依赖 location 对象
    
    return <KeepAliveRouteOutlet activeCacheKey={activeCacheKey} />;
};

export default MainRouteWrapper;
