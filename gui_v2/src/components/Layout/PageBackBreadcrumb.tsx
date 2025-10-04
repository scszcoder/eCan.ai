import React, { useMemo } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Button, Breadcrumb } from 'antd';
import { ArrowLeftOutlined, HomeOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useOrgStore } from '../../stores/orgStore';

// ==================== 类型定义 ====================
interface BreadcrumbItem {
    key: string;
    title: React.ReactNode;
    path?: string;
}

interface PathHandler {
    // 检查是否匹配该路径
    match: (segments: string[], path: string) => boolean;
    // 生成面包屑项（添加 context 参数用于传递组件数据）
    generate: (segments: string[], path: string, t: any, navigate: any, context?: any) => BreadcrumbItem[];
}

// ==================== 工具函数 ====================
// 查找树节点
function findTreeNodeById(node: any, targetId: string): any | null {
    if (node.id === targetId) {
        return node;
    }
    if (!node.children || node.children.length === 0) {
        return null;
    }
    for (const child of node.children) {
        const found = findTreeNodeById(child, targetId);
        if (found) return found;
    }
    return null;
}

// 创建可点击的链接
function createClickableLink(text: string, path: string, navigate: any): React.ReactNode {
    return (
        <span 
            style={{ 
                cursor: 'pointer', 
                color: 'rgba(96, 165, 250, 0.9)',
                transition: 'color 0.2s'
            }} 
            onClick={() => navigate(path)}
            onMouseEnter={(e) => e.currentTarget.style.color = 'rgba(147, 197, 253, 1)'}
            onMouseLeave={(e) => e.currentTarget.style.color = 'rgba(96, 165, 250, 0.9)'}
        >
            {text}
        </span>
    );
}

// 创建当前节点（不可点击）
function createCurrentNode(text: string): React.ReactNode {
    return <span style={{ color: 'rgba(255, 255, 255, 0.85)' }}>{text}</span>;
}

// ==================== Agents 路径处理器 ====================
const agentsPathHandler: PathHandler = {
    match: (segments) => segments[0] === 'agents',
    
    generate: (_segments, path, t, navigate, context) => {
        console.log('[PageBackBreadcrumb] Generating breadcrumb for path:', path);
        const items: BreadcrumbItem[] = [];
        const treeOrgs = context?.treeOrgs || [];
        const rootNode = treeOrgs[0];
        console.log('[PageBackBreadcrumb] rootNode:', rootNode?.name);
        
        // 添加 Agents 根节点
        items.push({
            key: '/agents',
            title: (
                <span 
                    style={{ 
                        cursor: 'pointer', 
                        color: 'rgba(96, 165, 250, 0.9)', 
                        display: 'flex', 
                        alignItems: 'center', 
                        gap: '4px',
                        transition: 'color 0.2s'
                    }} 
                    onClick={() => navigate('/agents')}
                    onMouseEnter={(e) => e.currentTarget.style.color = 'rgba(147, 197, 253, 1)'}
                    onMouseLeave={(e) => e.currentTarget.style.color = 'rgba(96, 165, 250, 0.9)'}
                >
                    <HomeOutlined />
                    {rootNode?.name || t('menu.agents')}
                </span>
            ),
            path: '/agents'
        });
        
        // 解析 organization 路径
        const orgMatches = path.match(/organization\/([^/]+)/g);
        if (orgMatches && rootNode) {
            let currentPath = '/agents';
            orgMatches.forEach((match, index) => {
                const orgId = match.replace('organization/', '');
                const node = findTreeNodeById(rootNode, orgId);
                
                if (node) {
                    currentPath += `/organization/${orgId}`;
                    const isLast = index === orgMatches.length - 1 && !path.includes('/details/');
                    
                    items.push({
                        key: currentPath,
                        title: isLast 
                            ? createCurrentNode(node.name)
                            : createClickableLink(node.name, currentPath, navigate),
                        path: isLast ? undefined : currentPath
                    });
                }
            });
        }
        
        // 如果是 details 页面或 add 页面，尝试从URL参数获取orgId
        if (path.includes('/details/') || path.includes('/add')) {
            // 从URL中获取orgId参数
            const urlParams = new URLSearchParams(window.location.search);
            const orgIdParam = urlParams.get('orgId');
            console.log('[PageBackBreadcrumb] URL orgId param:', orgIdParam);
            console.log('[PageBackBreadcrumb] orgMatches:', orgMatches);
            
            if (orgIdParam && rootNode && !orgMatches) {
                // 如果URL中有orgId但路径中没有organization，构建组织路径
                const node = findTreeNodeById(rootNode, orgIdParam);
                if (node) {
                    // 构建从根到当前组织的完整路径
                    const buildOrgPath = (targetNode: any, currentNode: any, pathSoFar: any[] = []): any[] | null => {
                        if (currentNode.id === targetNode.id) {
                            return [...pathSoFar, currentNode];
                        }
                        if (currentNode.children) {
                            for (const child of currentNode.children) {
                                const result = buildOrgPath(targetNode, child, [...pathSoFar, currentNode]);
                                if (result) return result;
                            }
                        }
                        return null;
                    };
                    
                    const orgPath = buildOrgPath(node, rootNode);
                    console.log('[PageBackBreadcrumb] Built org path:', orgPath?.map(n => n.name));
                    if (orgPath) {
                        // 添加组织路径的面包屑（跳过根节点，因为已经添加了）
                        orgPath.slice(1).forEach((orgNode) => {
                            const orgPathStr = `/agents/organization/${orgNode.id}`;
                            console.log('[PageBackBreadcrumb] Adding org breadcrumb:', orgNode.name, orgPathStr);
                            items.push({
                                key: orgPathStr,
                                title: createClickableLink(orgNode.name, orgPathStr, navigate),
                                path: orgPathStr
                            });
                        });
                    }
                } else {
                    console.log('[PageBackBreadcrumb] Node not found for orgId:', orgIdParam);
                }
            } else {
                console.log('[PageBackBreadcrumb] Conditions not met - orgIdParam:', orgIdParam, 'rootNode:', !!rootNode, 'orgMatches:', orgMatches);
            }
            
            // 添加详情/新增页面标题
            items.push({
                key: path,
                title: createCurrentNode(
                    path.includes('/add') 
                        ? t('pages.agents.create_agent', 'Create Agent')
                        : t('pages.agents.agent_details', 'Agent Details')
                )
            });
        }
        
        console.log('[PageBackBreadcrumb] Final breadcrumb items:', items.length);
        return items;
    }
};

// ==================== 默认路径处理器 ====================
const defaultPathHandler: PathHandler = {
    match: () => true, // 匹配所有路径
    
    generate: (segments, _path, t, navigate) => {
        const items: BreadcrumbItem[] = [];
        
        segments.forEach((seg, idx) => {
            const segPath = '/' + segments.slice(0, idx + 1).join('/');
            const isLast = idx === segments.length - 1;
            
            // 尝试翻译
            let label = t(`breadcrumb.${seg}`);
            if (label === `breadcrumb.${seg}`) {
                // 如果没有翻译，尝试菜单翻译
                label = t(`menu.${seg}`);
                if (label === `menu.${seg}`) {
                    // 如果还是没有，使用原始值并解码
                    label = decodeURIComponent(seg);
                }
            }
            
            items.push({
                key: segPath,
                title: isLast 
                    ? createCurrentNode(label)
                    : createClickableLink(label, segPath, navigate),
                path: isLast ? undefined : segPath
            });
        });
        
        return items;
    }
};

// ==================== 路径处理器注册表 ====================
const pathHandlers: PathHandler[] = [
    agentsPathHandler,
    // 可以在这里添加其他模块的处理器
    // tasksPathHandler,
    // skillsPathHandler,
    // ...
    defaultPathHandler, // 默认处理器放在最后
];

// ==================== 主组件 ====================
const PageBackBreadcrumb: React.FC = () => {
    const navigate = useNavigate();
    const location = useLocation();
    const { t } = useTranslation();
    const { treeOrgs } = useOrgStore(); // 在组件中获取数据
    const path = location.pathname;
    
    // 解析路径段
    const segments = path.split('/').filter(Boolean);
    
    // 构建面包屑项 - 使用处理器模式
    const items = useMemo(() => {
        // 找到第一个匹配的处理器
        const handler = pathHandlers.find(h => h.match(segments, path));
        
        // 准备上下文数据
        const context = {
            treeOrgs
        };
        
        // 使用处理器生成面包屑项
        return handler ? handler.generate(segments, path, t, navigate, context) : [];
    }, [path, segments, t, navigate, treeOrgs]);
    
    // 计算返回路径
    const parentPath = useMemo(() => {
        // 如果是组织详情页，返回到组织列表
        if (path.includes('/organization/')) {
            const lastOrgIndex = path.lastIndexOf('/organization/');
            return path.substring(0, lastOrgIndex) || '/agents';
        }
        // 默认返回上一级
        return '/' + segments.slice(0, -1).join('/');
    }, [path, segments]);
    
    // 总是显示面包屑（包括根目录）
    // 只有在非根目录时显示返回按钮
    const showBackButton = segments.length >= 2;
    
    return (
        <div style={{ 
            display: 'flex', 
            alignItems: 'center', 
            gap: 12
        }}>
            {showBackButton && (
                <Button
                    type="text"
                    icon={<ArrowLeftOutlined />}
                    onClick={() => navigate(parentPath)}
                    style={{ 
                        color: 'rgba(255, 255, 255, 0.85)',
                        paddingLeft: 0,
                        fontSize: '14px'
                    }}
                >
                    {t('common.back', '返回')}
                </Button>
            )}
            {items.length > 0 && (
                <Breadcrumb 
                    items={items as any}
                    style={{
                        color: 'rgba(255, 255, 255, 0.65)'
                    }}
                    itemRender={(item, params, items, paths) => {
                        const isLast = params.index === items.length - 1;
                        if (isLast || !item.path) {
                            return <span style={{ color: 'rgba(255, 255, 255, 0.85)' }}>{item.title}</span>;
                        }
                        return (
                            <span 
                                style={{ 
                                    cursor: 'pointer', 
                                    color: 'rgba(96, 165, 250, 0.9)',
                                    transition: 'color 0.2s'
                                }} 
                                onClick={(e) => {
                                    e.preventDefault();
                                    navigate(item.path as string);
                                }}
                                onMouseEnter={(e) => e.currentTarget.style.color = 'rgba(147, 197, 253, 1)'}
                                onMouseLeave={(e) => e.currentTarget.style.color = 'rgba(96, 165, 250, 0.9)'}
                            >
                                {item.title}
                            </span>
                        );
                    }}
                />
            )}
        </div>
    );
};

export default PageBackBreadcrumb; 