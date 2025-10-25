import React, { useMemo } from 'react';
import { useLocation } from 'react-router-dom';
import KeepAliveRouteOutlet from 'keepalive-for-react-router';

/**
 * Agents 路由包装器
 * 
 * 为 agents 子路由提供统一的 KeepAlive 缓存 key 管理
 * 
 * 问题：
 * - /agents/organization/:orgId/* 是动态路由，包含子路径
 * - 默认情况下，每个不同的 orgId 或子路径都会创建新的缓存实例
 * - 这导致在不同组织间切换或进入子节点时，OrgNavigator 组件会重新渲染，丢失状态
 * 
 * 解决方案：
 * - /agents 根路径和所有 /agents/organization/* 路径共享同一个缓存 key: '/agents'
 * - OrgNavigator 组件通过 actualOrgId（只依赖 location.pathname）来区分显示内容
 * - 这样可以在保持组件实例的同时，正确响应 URL 变化
 * - 其他路径（如 /agents/details/:id、/agents/add）使用各自的路径作为 cache key
 * 
 * 示例：
 * - /agents → cache key: '/agents'（共享缓存）
 * - /agents/organization/org1 → cache key: '/agents'（共享缓存）
 * - /agents/organization/org1/subnode → cache key: '/agents'（共享缓存）
 * - /agents/organization/org2 → cache key: '/agents'（共享缓存）
 * - /agents/details/123 → cache key: '/agents/details/123'（独立缓存）
 */
const AgentsRouteWrapper: React.FC = () => {
    const location = useLocation();
    // ⚠️ 关键优化：提取字符串，避免 location 对象引用变化导致重复渲染
    const pathname = location.pathname;
    const search = location.search;
    
    // 计算当前路由的 cache key
    const activeCacheKey = useMemo(() => {
        // /agents 根路径和所有 organization 路径共享同一个 cache key
        // 因为 actualOrgId 现在只依赖 pathname，不依赖 useParams
        // 所以可以安全地共享缓存实例
        if (pathname === '/agents' || pathname.startsWith('/agents/organization')) {
            return '/agents';
        }
        // 其他路径使用完整路径作为 cache key
        return pathname + search;
    }, [pathname, search]); // ⚠️ 只依赖字符串，不依赖 location 对象
    
    return <KeepAliveRouteOutlet activeCacheKey={activeCacheKey} />;
};

export default AgentsRouteWrapper;
