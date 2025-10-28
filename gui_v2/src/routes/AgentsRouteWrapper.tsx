import React, { useMemo } from 'react';
import { useLocation } from 'react-router-dom';
import KeepAliveRouteOutlet from 'keepalive-for-react-router';

/**
 * Agents 路由包装器
 * 
 * 为 agents 子路由提供统一的 KeepAlive Cache key 管理
 * 
 * 问题：
 * - /agents/organization/:orgId/* 是动态路由，Include子Path
 * - Default情况下，每个不同的 orgId 或子Path都会Create新的Cache实例
 * - 这导致在不同组织间Toggle或进入子节点时，OrgNavigator Component会重新Render，丢失Status
 * 
 * 解决方案：
 * - /agents 根Path和All /agents/organization/* Path共享同一个Cache key: '/agents'
 * - OrgNavigator Component通过 actualOrgId（只Dependency location.pathname）来区分DisplayContent
 * - 这样Can在保持Component实例的同时，正确Response URL 变化
 * - 其他Path（如 /agents/details/:id、/agents/add）使用各自的Path作为 cache key
 * 
 * Example：
 * - /agents → cache key: '/agents'（共享Cache）
 * - /agents/organization/org1 → cache key: '/agents'（共享Cache）
 * - /agents/organization/org1/subnode → cache key: '/agents'（共享Cache）
 * - /agents/organization/org2 → cache key: '/agents'（共享Cache）
 * - /agents/details/123 → cache key: '/agents/details/123'（独立Cache）
 */
const AgentsRouteWrapper: React.FC = () => {
    const location = useLocation();
    // ⚠️ 关键Optimize：提取字符串，避免 location 对象Reference变化导致重复Render
    const pathname = location.pathname;
    const search = location.search;
    
    // 计算When前路由的 cache key
    const activeCacheKey = useMemo(() => {
        // /agents 根Path和All organization Path共享同一个 cache key
        // 因为 actualOrgId 现在只Dependency pathname，不Dependency useParams
        // 所以CanSecurity地共享Cache实例
        if (pathname === '/agents' || pathname.startsWith('/agents/organization')) {
            return '/agents';
        }
        // 其他Path使用完整Path作为 cache key
        return pathname + search;
    }, [pathname, search]); // ⚠️ 只Dependency字符串，不Dependency location 对象
    
    return <KeepAliveRouteOutlet activeCacheKey={activeCacheKey} />;
};

export default AgentsRouteWrapper;
