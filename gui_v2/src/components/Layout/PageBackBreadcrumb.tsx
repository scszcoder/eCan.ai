import React, { useMemo, useState, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Button, Breadcrumb, Tooltip, App, Input } from 'antd';
import { ArrowLeftOutlined, HomeOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import styled from '@emotion/styled';
import { useOrgStore } from '../../stores/orgStore';
import { useTaskStore } from '../../stores/domain/taskStore';
import { useSkillStore } from '../../stores/domain/skillStore';
import { useUserStore } from '../../stores/userStore';
import { get_ipc_api } from '@/services/ipc_api';

// ==================== 样式组件 ====================
const BreadcrumbContainer = styled.div`
    display: flex;
    align-items: center;
    gap: 16px;
    justify-content: space-between;
    width: 100%;
`;

const LeftSection = styled.div`
    display: flex;
    align-items: center;
    gap: 16px;
    flex: 1;
    min-width: 0;
`;

const RightSection = styled.div`
    display: flex;
    align-items: center;
    gap: 12px;
    flex-shrink: 0;
`;

const StyledBackButton = styled(Button)`
    color: rgba(203, 213, 225, 0.9) !important;
    padding-left: 0 !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    height: 32px !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    
    &:hover {
        color: rgba(248, 250, 252, 1) !important;
        background: rgba(255, 255, 255, 0.08) !important;
    }
    
    .anticon {
        transition: color 0.3s ease;
    }
`;

const StyledBreadcrumb = styled(Breadcrumb)`
    .ant-breadcrumb-separator {
        color: rgba(148, 163, 184, 0.5) !important;
        margin: 0 8px !important;
    }
    
    .ant-breadcrumb-link {
        color: rgba(203, 213, 225, 0.85) !important;
        transition: all 0.3s ease !important;
        font-size: 14px !important;
        font-weight: 500 !important;
    }
`;

const BreadcrumbLink = styled.span<{ $isClickable?: boolean }>`
    cursor: ${props => props.$isClickable ? 'pointer' : 'default'};
    color: ${props => props.$isClickable 
        ? 'rgba(96, 165, 250, 0.95)' 
        : 'rgba(248, 250, 252, 0.95)'} !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    font-weight: ${props => props.$isClickable ? '500' : '600'};
    display: flex;
    align-items: center;
    gap: 6px;
    
    ${props => props.$isClickable && `
        &:hover {
            color: rgba(147, 197, 253, 1) !important;
        }
    `}
    
    .anticon {
        font-size: 16px;
    }
`;

const StyledSearchInput = styled(Input)`
    width: 280px;
    height: 36px !important;
    background: rgba(51, 65, 85, 0.3) !important;
    border: none !important;
    border-radius: 8px !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.2);
    padding: 0 12px !important;
    line-height: 36px !important;
    
    &:hover {
        background: rgba(51, 65, 85, 0.5) !important;
        box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.3);
    }
    
    &:focus, &.ant-input-focused, &.ant-input-affix-wrapper-focused {
        background: rgba(51, 65, 85, 0.6) !important;
        box-shadow: 
            0 0 0 2px rgba(59, 130, 246, 0.15),
            inset 0 1px 3px rgba(0, 0, 0, 0.3) !important;
    }
    
    /* 内部输入框 */
    input {
        background: transparent !important;
        color: rgba(248, 250, 252, 0.95) !important;
        height: 34px !important;
        line-height: 34px !important;
        padding: 0 !important;
        border: none !important;
        
        &::placeholder {
            color: rgba(148, 163, 184, 0.6) !important;
        }
    }
    
    /* 前缀图标 */
    .ant-input-prefix {
        color: rgba(148, 163, 184, 0.8) !important;
        margin-right: 8px !important;
        display: flex;
        align-items: center;
        
        .anticon {
            font-size: 14px;
        }
    }
    
    /* 清除按钮 */
    .ant-input-clear-icon {
        color: rgba(148, 163, 184, 0.6) !important;
        font-size: 12px;
        
        &:hover {
            color: rgba(203, 213, 225, 0.9) !important;
        }
    }
    
    /* 后缀区域 */
    .ant-input-suffix {
        display: flex;
        align-items: center;
        margin-left: 4px;
    }
`;

const StyledRefreshButton = styled(Button)`
    color: rgba(203, 213, 225, 0.9) !important;
    font-size: 16px !important;
    width: 36px !important;
    height: 36px !important;
    padding: 0 !important;
    border-radius: 8px !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    display: flex;
    align-items: center;
    justify-content: center;
    
    &:hover:not(:disabled) {
        color: rgba(248, 250, 252, 1) !important;
        background: rgba(59, 130, 246, 0.15) !important;
    }
    
    &:active:not(:disabled) {
        opacity: 0.8;
    }
    
    &:disabled {
        opacity: 0.5;
    }
`;

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
        <BreadcrumbLink 
            $isClickable={true}
            onClick={() => navigate(path)}
        >
            {text}
        </BreadcrumbLink>
    );
}

// 创建当前节点（不可点击）
function createCurrentNode(text: string): React.ReactNode {
    return <BreadcrumbLink $isClickable={false}>{text}</BreadcrumbLink>;
}

// ==================== Agents 路径处理器 ====================
const agentsPathHandler: PathHandler = {
    match: (segments) => segments[0] === 'agents',
    
    generate: (_segments, path, t, navigate, context) => {
        console.log('[PageBackBreadcrumb] Generating breadcrumb for path:', path);
        const items: BreadcrumbItem[] = [];
        const treeOrgs = context?.treeOrgs || [];
        const searchParams = context?.searchParams;
        const rootNode = treeOrgs[0];
        console.log('[PageBackBreadcrumb] rootNode:', rootNode?.name);
        
        // 添加 Agents 根节点
        items.push({
            key: '/agents',
            title: (
                <BreadcrumbLink 
                    $isClickable={true}
                    onClick={() => navigate('/agents')}
                >
                    <HomeOutlined />
                    {rootNode?.name || t('menu.agents')}
                </BreadcrumbLink>
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
            const orgIdParam = searchParams?.get('orgId');
            console.log('[PageBackBreadcrumb] URL orgId param:', orgIdParam);
            console.log('[PageBackBreadcrumb] orgMatches:', orgMatches);

            if (orgIdParam && rootNode) {
                // 如果URL中有orgId，构建组织路径
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
                        // 如果路径中已经有organization段，则不重复添加
                        if (!orgMatches) {
                            // 添加组织路径的面包屑（跳过根节点，因为已经添加了）
                            let currentOrgPath = '/agents';
                            orgPath.slice(1).forEach((orgNode) => {
                                currentOrgPath += `/organization/${orgNode.id}`;
                                console.log('[PageBackBreadcrumb] Adding org breadcrumb:', orgNode.name, currentOrgPath);
                                items.push({
                                    key: currentOrgPath,
                                    title: createClickableLink(orgNode.name, currentOrgPath, navigate),
                                    path: currentOrgPath
                                });
                            });
                        }
                    }
                } else {
                    console.log('[PageBackBreadcrumb] Node not found for orgId:', orgIdParam);
                }
            } else {
                console.log('[PageBackBreadcrumb] Conditions not met - orgIdParam:', orgIdParam, 'rootNode:', !!rootNode);
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
interface PageBackBreadcrumbProps {
    searchQuery?: string;
    onSearchChange?: (query: string) => void;
}

const PageBackBreadcrumb: React.FC<PageBackBreadcrumbProps> = ({ searchQuery = '', onSearchChange }) => {
    const navigate = useNavigate();
    const location = useLocation();
    const { t } = useTranslation();
    const { message } = App.useApp();
    const { treeOrgs } = useOrgStore(); // 在组件中获取数据
    const username = useUserStore((state) => state.username);
    const path = location.pathname;
    const [refreshing, setRefreshing] = useState(false);
    
    // 解析路径段 - 需要在 handleRefresh 之前定义
    const segments = path.split('/').filter(Boolean);

    // 处理刷新数据 - 根据当前页面智能刷新
    const handleRefresh = useCallback(async () => {
        if (refreshing || !username) return;
        
        setRefreshing(true);
        try {
            const api = get_ipc_api();
            const currentPath = segments[0];
            
            // 根据当前页面刷新对应的数据
            if (currentPath === 'agents') {
                // Agents 页面：调用 get_all_org_agents 接口刷新组织和代理数据
                const res = await api.getAllOrgAgents(username).catch((e: any) => ({ success: false, error: e, data: null }));
                
                if (res.success && res.data) {
                    useOrgStore.getState().refreshOrgData();
                }
            } else if (currentPath === 'tasks') {
                // Tasks 页面：只刷新 tasks 数据
                const tasksRes = await api.getAgentTasks(username, []).catch((e: any) => ({ success: false, error: e, data: null }));
                
                if (tasksRes.success && tasksRes.data && (tasksRes.data as any).tasks) {
                    useTaskStore.getState().setItems((tasksRes.data as any).tasks);
                }
            } else if (currentPath === 'skills') {
                // Skills 页面：只刷新 skills 数据
                const skillsRes = await api.getAgentSkills(username, []).catch((e: any) => ({ success: false, error: e, data: null }));
                
                if (skillsRes.success && skillsRes.data && (skillsRes.data as any).skills) {
                    useSkillStore.getState().setItems((skillsRes.data as any).skills);
                }
            }
            
            message.success(t('common.refresh_success') || '数据刷新成功');
        } catch (error) {
            console.error('[PageBackBreadcrumb] Refresh error:', error);
            message.error(t('common.refresh_failed') || '数据刷新失败');
        } finally {
            setRefreshing(false);
        }
    }, [refreshing, username, message, t, segments]);

    // 从 location.search 获取查询参数
    const searchParams = useMemo(() => new URLSearchParams(location.search), [location.search]);
    
    // 构建面包屑项 - 使用处理器模式
    const items = useMemo(() => {
        // 找到第一个匹配的处理器
        const handler = pathHandlers.find(h => h.match(segments, path));

        // 准备上下文数据
        const context = {
            treeOrgs,
            searchParams
        };

        // 使用处理器生成面包屑项
        return handler ? handler.generate(segments, path, t, navigate, context) : [];
    }, [path, segments, t, navigate, treeOrgs, searchParams]);
    
    // 计算返回路径
    const parentPath = useMemo(() => {
        // 如果是 details 或 add 页面，检查是否有 orgId 参数
        if (path.includes('/details/') || path.includes('/add')) {
            const orgIdParam = searchParams.get('orgId');
            if (orgIdParam) {
                // 返回到对应的组织页面
                // 需要构建完整的组织路径
                const rootNode = treeOrgs[0];
                if (rootNode) {
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
                        if (orgPath && orgPath.length > 1) {
                            // 构建完整的组织路径
                            let fullOrgPath = '/agents';
                            orgPath.slice(1).forEach((orgNode) => {
                                fullOrgPath += `/organization/${orgNode.id}`;
                            });
                            return fullOrgPath;
                        }
                    }
                }
                // 如果找不到节点，返回到 agents 根页面
                return '/agents';
            }
        }

        // 如果是组织详情页，返回到组织列表
        if (path.includes('/organization/')) {
            const lastOrgIndex = path.lastIndexOf('/organization/');
            return path.substring(0, lastOrgIndex) || '/agents';
        }
        // 默认返回上一级
        return '/' + segments.slice(0, -1).join('/');
    }, [path, segments, treeOrgs, searchParams]);
    
    // 总是显示面包屑（包括根目录）
    // 只有在非根目录时显示返回按钮
    const showBackButton = segments.length >= 2;
    
    // 判断是否在 agents 页面（显示搜索框）
    const isAgentsPage = segments[0] === 'agents';
    
    return (
        <BreadcrumbContainer>
            <LeftSection>
                {showBackButton && (
                    <StyledBackButton
                        type="text"
                        icon={<ArrowLeftOutlined />}
                        onClick={() => navigate(parentPath)}
                    >
                        {t('common.back', '返回')}
                    </StyledBackButton>
                )}
                {items.length > 0 && (
                    <StyledBreadcrumb 
                        items={items as any}
                        itemRender={(item, params, items) => {
                            const isLast = params.index === items.length - 1;
                            if (isLast || !item.path) {
                                return item.title;
                            }
                            return (
                                <BreadcrumbLink 
                                    $isClickable={true}
                                    onClick={(e) => {
                                        e.preventDefault();
                                        navigate(item.path as string);
                                    }}
                                >
                                    {item.title}
                                </BreadcrumbLink>
                            );
                        }}
                    />
                )}
            </LeftSection>
            
            <RightSection>
                {/* 搜索框 - 仅在 agents 页面显示 */}
                {isAgentsPage && onSearchChange && (
                    <StyledSearchInput
                        placeholder={t('pages.agents.search_placeholder') || '请输入名称或其他关键字'}
                        prefix={<SearchOutlined />}
                        value={searchQuery}
                        onChange={(e) => onSearchChange(e.target.value)}
                        allowClear
                    />
                )}
                
                {/* 刷新按钮 */}
                <Tooltip title={t('common.refresh') || '刷新数据'}>
                    <StyledRefreshButton
                        type="text"
                        icon={<ReloadOutlined spin={refreshing} />}
                        onClick={handleRefresh}
                        disabled={refreshing}
                    />
                </Tooltip>
            </RightSection>
        </BreadcrumbContainer>
    );
};

export default PageBackBreadcrumb; 