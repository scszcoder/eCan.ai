import React, { useMemo } from 'react';
import { useLocation, useOutlet, Outlet } from 'react-router-dom';
import { KeepAlive } from 'keepalive-for-react';

/**
 * 主路由包装器 - 管理 KeepAlive 缓存策略
 * 
 * 在 file:// 协议下（PyInstaller 环境），KeepAlive 缓存会导致路由导航失效，
 * 因此直接使用 Outlet 绕过缓存。
 * 
 * 在 http:// 协议下（开发环境），使用 KeepAlive 提升性能：
 * - /chat → 固定 key '/chat'
 * - /agents/* → 固定 key '/agents'
 * - /knowledge-ported → 固定 key '/knowledge-ported'
 * - 其他 → pathname + search
 */

// 检测是否在 file:// 协议下运行（PyInstaller 环境）
const isFileProtocol = typeof window !== 'undefined' && window.location.protocol === 'file:';

// file:// 协议下的简单包装器
const FileProtocolWrapper: React.FC = () => <Outlet />;

// http:// 协议下的 KeepAlive 包装器
const HttpProtocolWrapper: React.FC = () => {
    const { pathname, search } = useLocation();
    const outlet = useOutlet();
    
    const activeCacheKey = useMemo(() => {
        if (pathname === '/chat') return '/chat';
        if (pathname === '/skills') return '/skills';
        if (pathname === '/tasks') return '/tasks';
        if (pathname === '/knowledge-ported') return '/knowledge-ported';
        if (pathname === '/agents' || pathname.startsWith('/agents/')) return '/agents';
        return pathname + search;
    }, [pathname, search]);
    
    return (
        <KeepAlive activeCacheKey={activeCacheKey} max={20}>
            {outlet}
        </KeepAlive>
    );
};

// 根据协议选择包装器
const MainRouteWrapper: React.FC = isFileProtocol ? FileProtocolWrapper : HttpProtocolWrapper;

export default MainRouteWrapper;
