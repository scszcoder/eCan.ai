import React, { useMemo, useCallback, useEffect } from 'react';
import { Spin, Alert } from 'antd';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useUserStore } from '../../stores/userStore';
import Door from './components/Door';
import './VirtualPlatform.css';
import { useOrgStore } from '../../stores/orgStore';
import { useAgentStore } from '../../stores/agentStore';
import { logger } from '../../utils/logger';
import { get_ipc_api } from '@/services/ipc_api';
import { DisplayNode, GetAllOrgAgentsResponse } from '../Orgs/types';
import { useOrgAgentsUpdate } from './hooks/useOrgAgentsUpdate';

function getGridTemplate(deptCount: number) {
  // 2~4个门：2列，5~6个：3列，7~9个：3列，10+：4列
  if (deptCount <= 4) return 'repeat(2, 1fr)';
  if (deptCount <= 6) return 'repeat(3, 1fr)';
  if (deptCount <= 9) return 'repeat(3, 1fr)';
  return 'repeat(4, 1fr)';
}

const satelliteDots = [
  {cx: 180, cy: 120, r: 6}, {cx: 320, cy: 90, r: 4}, {cx: 1050, cy: 180, r: 7},
  {cx: 900, cy: 120, r: 5}, {cx: 200, cy: 700, r: 5}, {cx: 1100, cy: 600, r: 6},
  {cx: 1000, cy: 400, r: 4}, {cx: 800, cy: 720, r: 5}, {cx: 400, cy: 720, r: 4},
  {cx: 600, cy: 100, r: 7}, {cx: 100, cy: 400, r: 5}, {cx: 1150, cy: 350, r: 4}
];

const VirtualPlatform: React.FC = () => {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const username = useUserStore((state) => state.username);
  
  // Organization store
  const { 
    displayNodes, 
    loading, 
    error, 
    setAllOrgAgents, 
    setLoading, 
    setError, 
    shouldFetchData 
  } = useOrgStore();
  
  // Agent store
  const setAgents = useAgentStore((state) => state.setAgents);

  const itemCount = displayNodes.length;
  // 使用 useMemo 缓存计算结果，避免每次渲染重新计算
  const gridTemplate = useMemo(() => getGridTemplate(itemCount), [itemCount]);

  // Fetch organization structure data (组织架构 + Agent 数据)
  const fetchOrgStructure = useCallback(async () => {
    if (!username || !shouldFetchData()) return;

    setLoading(true);
    setError(null);
    
    try {
      logger.info('[VirtualPlatform] Fetching organization structure...');
      // 调用新的整合接口 getAllOrgAgents
      const response = await get_ipc_api().getAllOrgAgents<GetAllOrgAgentsResponse>(username);
      
      if (response.success && response.data) {
        // 保存完整的组织结构数据到 orgStore
        setAllOrgAgents(response.data);
        
        // 从组织结构中提取 agents 并转换为 agentStore 期望的格式
        const extractAllAgents = (node: any): any[] => {
          let allAgents: any[] = [];
          
          if (node.agents && Array.isArray(node.agents)) {
            const transformedAgents = node.agents.map((agent: any) => ({
              card: {
                id: agent.id,
                name: agent.name,
                description: agent.description,
                avatar: agent.avatar,
                status: agent.status
              },
              ...agent
            }));
            allAgents.push(...transformedAgents);
          }
          
          if (node.children && Array.isArray(node.children)) {
            node.children.forEach((child: any) => {
              const childAgents = extractAllAgents(child);
              allAgents.push(...childAgents);
            });
          }
          
          return allAgents;
        };
        
        const allAgents = extractAllAgents(response.data.orgs);
        
        // 保存 agents 数据到 agentStore
        if (allAgents.length > 0) {
          setAgents(allAgents);
          logger.info(`[VirtualPlatform] Extracted and saved ${allAgents.length} agents to agentStore`);
        } else {
          logger.warn('[VirtualPlatform] No agents found in organization structure');
        }
        
        // 从树形结构中统计 agents 数量
        const countAgentsInTree = (node: any): { assigned: number, unassigned: number } => {
          let assigned = 0;
          let unassigned = 0;
          
          // 统计当前节点的 agents
          if (node.agents) {
            node.agents.forEach((agent: any) => {
              if (agent.org_id) {
                assigned++;
              } else {
                unassigned++;
              }
            });
          }
          
          // 递归统计子节点的 agents
          if (node.children) {
            node.children.forEach((child: any) => {
              const childCounts = countAgentsInTree(child);
              assigned += childCounts.assigned;
              unassigned += childCounts.unassigned;
            });
          }
          
          return { assigned, unassigned };
        };
        
        const { assigned: assignedCount, unassigned: unassignedCount } = countAgentsInTree(response.data.orgs);
        logger.info(`[VirtualPlatform] Successfully loaded tree structure with ${assignedCount} assigned agents, ${unassignedCount} unassigned agents`);
      } else {
        const errorMsg = response.error?.message || 'Failed to fetch organization structure';
        setError(errorMsg);
        logger.error('[VirtualPlatform] Failed to fetch organization structure:', errorMsg);
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error occurred';
      setError(errorMessage);
      logger.error('[VirtualPlatform] Error fetching organization structure:', errorMessage);
    } finally {
      setLoading(false);
    }
  }, [username, setAllOrgAgents, setAgents, setLoading, setError, shouldFetchData]);

  useEffect(() => {
    fetchOrgStructure();
  }, [fetchOrgStructure]);

  // 强制刷新组织数据的回调（绕过缓存检查）
  const forceRefreshOrgStructure = useCallback(async () => {
    if (!username) return;

    logger.info('[VirtualPlatform] Force refreshing organization structure...');
    setLoading(true);
    setError(null);
    
    try {
      // 直接调用 API，不检查 shouldFetchData
      const response = await get_ipc_api().getAllOrgAgents<GetAllOrgAgentsResponse>(username);
      
      if (response.success && response.data) {
        // 保存完整的组织结构数据到 orgStore
        setAllOrgAgents(response.data);
        
        // 从组织结构中提取 agents 并转换为 agentStore 期望的格式
        const extractAllAgents = (node: any): any[] => {
          let allAgents: any[] = [];
          
          if (node.agents && Array.isArray(node.agents)) {
            const transformedAgents = node.agents.map((agent: any) => ({
              card: {
                id: agent.id,
                name: agent.name,
                description: agent.description,
                avatar: agent.avatar,
                status: agent.status
              },
              ...agent
            }));
            allAgents.push(...transformedAgents);
          }
          
          if (node.children && Array.isArray(node.children)) {
            node.children.forEach((child: any) => {
              const childAgents = extractAllAgents(child);
              allAgents.push(...childAgents);
            });
          }
          
          return allAgents;
        };
        
        const allAgents = extractAllAgents(response.data.orgs);
        
        // 保存 agents 数据到 agentStore
        if (allAgents.length > 0) {
          setAgents(allAgents);
          logger.info(`[VirtualPlatform] Force refreshed and saved ${allAgents.length} agents to agentStore`);
        }
        
        logger.info('[VirtualPlatform] Organization structure force refreshed successfully');
      } else {
        const errorMessage = response.error?.message || 'Failed to fetch organization structure';
        setError(errorMessage);
        logger.error('[VirtualPlatform] Error in force refresh response:', errorMessage);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred';
      setError(errorMessage);
      logger.error('[VirtualPlatform] Error force refreshing organization structure:', errorMessage);
    } finally {
      setLoading(false);
    }
  }, [username, setAllOrgAgents, setLoading, setError]);

  // 使用自定义 Hook 监听组织数据更新事件
  useOrgAgentsUpdate(forceRefreshOrgStructure, [forceRefreshOrgStructure], 'VirtualPlatform');

  // 处理不同类型的点击事件
  const handleNodeClick = useCallback((node: DisplayNode) => {
    if (node.type === 'org_with_children') {
      // 有子节点的组织：进入子级页面（将来实现层级导航）
      navigate(`/agents/room/${node.id}`);
    } else if (node.type === 'org_with_agents') {
      // 有 Agent 的组织：查看该组织的 Agent 列表
      navigate(`/agents/room/${node.id}`);
    } else if (node.type === 'unassigned_agents') {
      // 未分配的 Agent：查看未分配 Agent 列表
      navigate(`/agents/room/unassigned`);
    }
  }, [navigate]);

  // 使用 useMemo 缓存门组件的渲染，避免每次重新创建
  const doorComponents = useMemo(() => {
    return displayNodes.map((node, index) => {
      // 处理国际化键翻译
      let displayName = node.name;
      
      // 如果是国际化键，进行翻译
      if (node.name.startsWith('pages.')) {
        displayName = t(node.name) || node.name;
      }
      
      // 根据节点类型添加后缀
      if (node.type === 'org_with_agents' && node.agentCount) {
        displayName = `${displayName} (${node.agentCount})`;
      } else if (node.type === 'unassigned_agents') {
        displayName = `${displayName} (${node.agentCount || 0})`;
      }
      
      return (
        <div 
          key={`${node.type}-${node.id}-${index}`} 
          onClick={() => handleNodeClick(node)} 
          style={{cursor: 'pointer'}}
        >
          <Door 
            name={displayName}
          />
        </div>
      );
    });
  }, [displayNodes, handleNodeClick, t]);

  // Show loading state
  if (loading && displayNodes.length === 0) {
    return (
      <div className="virtual-platform">
        <div style={{ 
          display: 'flex', 
          justifyContent: 'center', 
          alignItems: 'center', 
          height: '100%',
          flexDirection: 'column',
          gap: '16px'
        }}>
          <Spin size="large" />
          <div style={{ color: 'var(--ant-color-text-secondary)' }}>
            Loading organizations...
          </div>
        </div>
      </div>
    );
  }

  // Show error state
  if (error && displayNodes.length === 0) {
    return (
      <div className="virtual-platform">
        <div style={{ 
          display: 'flex', 
          justifyContent: 'center', 
          alignItems: 'center', 
          height: '100%',
          padding: '20px'
        }}>
          <Alert
            message="Failed to load organizations"
            description={error}
            type="error"
            showIcon
            action={
              <button 
                onClick={fetchOrgStructure}
                style={{
                  background: 'var(--ant-primary-color)',
                  color: 'white',
                  border: 'none',
                  padding: '4px 12px',
                  borderRadius: '4px',
                  cursor: 'pointer'
                }}
              >
                Retry
              </button>
            }
          />
        </div>
      </div>
    );
  }

  return (
    <div className="virtual-platform">
      {/* SVG虚拟地板和网格 */}
      <svg className="virtual-bg-svg" width="100%" height="100%" viewBox="0 0 1200 800" style={{position:'absolute',left:0,top:0,zIndex:0}}>
        {/* 椭圆地板 */}
        <ellipse cx="600" cy="700" rx="420" ry="80" fill="var(--ant-primary-1, #e6f4ff)" opacity="0.7" />
        {/* 网格线条 */}
        {Array.from({length: 7}).map((_,i) => (
          <ellipse key={i} cx="600" cy="700" rx={180+i*40} ry={34+i*8} fill="none" stroke="var(--ant-primary-2, #91caff)" strokeWidth="1.5" opacity="0.18" />
        ))}
        {/* 径向发光线 */}
        {Array.from({length: 12}).map((_,i) => {
          const angle = (2*Math.PI*i)/12;
          return <line key={i} x1={600} y1={700} x2={600+420*Math.cos(angle)} y2={700+80*Math.sin(angle)} stroke="var(--ant-primary-2, #91caff)" strokeWidth="1.2" opacity="0.10" />
        })}
        {/* 智能节点 */}
        {[{cx:300,cy:200},{cx:900,cy:250},{cx:600,cy:400},{cx:400,cy:600},{cx:800,cy:650}].map((n,i)=>(
          <circle key={i} cx={n.cx} cy={n.cy} r="18" fill="var(--ant-primary-color, #1677ff)" opacity="0.18" filter="url(#glow)" />
        ))}
        {/* 卫星点 */}
        {satelliteDots.map((dot, i) => (
          <circle key={"sat"+i} cx={dot.cx} cy={dot.cy} r={dot.r} fill="var(--ant-primary-color, #1677ff)" opacity="0.32" filter="url(#glow)" />
        ))}
        {/* 数据流/流程线 */}
        <polyline points="300,200 600,400 900,250" fill="none" stroke="var(--ant-primary-color, #1677ff)" strokeWidth="3" opacity="0.13" />
        <polyline points="400,600 600,400 800,650" fill="none" stroke="var(--ant-primary-2, #91caff)" strokeWidth="2" opacity="0.10" />
        {/* AI脑波/光圈 */}
        <ellipse cx="600" cy="400" rx="80" ry="30" fill="none" stroke="var(--ant-primary-2, #91caff)" strokeWidth="2" opacity="0.10" />
        {/* SVG滤镜：发光 */}
        <defs>
          <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="8" result="coloredBlur"/>
            <feMerge>
              <feMergeNode in="coloredBlur"/>
              <feMergeNode in="SourceGraphic"/>
            </feMerge>
          </filter>
        </defs>
      </svg>
      {/* 光斑/灯光 */}
      <div className="virtual-bg-blur virtual-bg-blur1" />
      <div className="virtual-bg-blur virtual-bg-blur2" />
      {/* 门规则网格分布 */}
      <div className="doors-grid" style={{gridTemplateColumns: gridTemplate}}>
        {doorComponents}
      </div>
    </div>
  );
};

export default React.memo(VirtualPlatform); 