import React, { useCallback, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, Dropdown } from 'antd';
import { PlusOutlined, MoreOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import type { MenuProps } from 'antd';
import { useAgentStore } from '../../stores/agentStore';
import { useOrgStore } from '../../stores/orgStore';
import AgentAvatar from './components/AgentAvatar';
import './DepartmentRoom.css';
import { Agent } from './types';
import { findOrgById } from '../Orgs/types';
import { useTranslation } from 'react-i18next';

const DepartmentRoom: React.FC = () => {
  const { departmentId } = useParams<{ departmentId: string }>();
  const navigate = useNavigate();
  const agents = useAgentStore((state) => state.agents);
  const { t } = useTranslation();
  const { orgTree, agents: allOrgAgents, unassignedAgents } = useOrgStore();

  // Find current organization
  const currentOrganization = useMemo(() => {
    if (!departmentId || !orgTree.length) return null;
    return findOrgById(orgTree, departmentId);
  }, [departmentId, orgTree]);

  // 返回 doors 列表，使用 replace 避免页面闪烁
  const goBack = useCallback(() => {
    navigate('/agents', { replace: true }); // Navigate to parent route
  }, [navigate]);

  // Get agents for current organization from already loaded data
  const displayAgents = useMemo(() => {
    if (departmentId === 'unassigned') {
      // 显示未分配的 Agent
      return unassignedAgents.map((orgAgent): Agent => ({
        card: {
          id: orgAgent.id,
          name: orgAgent.name,
          description: orgAgent.description || '',
          url: '',
          provider: null,
          version: '1.0.0',
          documentationUrl: null,
          capabilities: {
            streaming: false,
            pushNotifications: false,
            stateTransitionHistory: false,
          },
          authentication: null,
          defaultInputModes: [],
          defaultOutputModes: [],
        },
        supervisors: [],
        subordinates: [],
        peers: [],
        rank: 'member',
        organizations: [],
        job_description: orgAgent.description || '',
        personalities: [],
      }));
    }

    // 获取当前组织的 Agent
    const orgAgents = allOrgAgents.filter(agent => agent.org_id === departmentId);
    
    if (orgAgents.length > 0) {
      // Convert OrgAgent to Agent format for compatibility
      return orgAgents.map((orgAgent): Agent => ({
        card: {
          id: orgAgent.id,
          name: orgAgent.name,
          description: orgAgent.description || '',
          url: '',
          provider: null,
          version: '1.0.0',
          documentationUrl: null,
          capabilities: {
            streaming: false,
            pushNotifications: false,
            stateTransitionHistory: false,
          },
          authentication: null,
          defaultInputModes: [],
          defaultOutputModes: [],
        },
        supervisors: [],
        subordinates: [],
        peers: [],
        rank: 'member',
        organizations: [departmentId || ''],
        job_description: orgAgent.description || '',
        personalities: [],
      }));
    }

    // Fallback to existing agents filtered by department
    return agents.filter((a: Agent) => {
      const dept = (a as any).departmentId || a.organizations?.[0];
      return departmentId ? dept === departmentId : true;
    });
  }, [departmentId, allOrgAgents, unassignedAgents, agents]);

  // 获取当前部门的名称
  const departmentName = useMemo(() => {
    if (departmentId === 'unassigned') {
      return t('pages.agents.unassigned_agents') || '未分配代理';
    }
    return currentOrganization?.name || departmentId || '';
  }, [currentOrganization, departmentId, t]);

  // 定义下拉菜单项
  const menuItems: MenuProps['items'] = [
    {
      key: 'add',
      label: (
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => navigate('/agents/details/new')} // Navigate to nested route
          className="dropdown-menu-button"
          style={{ width: '100%', textAlign: 'left' }}
        >
          {t('pages.agents.add') || 'Add'}
        </Button>
      ),
    },
  ];

  return (
    <div className="department-room" style={{ position: 'relative' }}>
      {/* Header bar with title (if any) and global Add button on the right */}
      <div className="header-section">
        <Button 
          icon={<ArrowLeftOutlined />} 
          onClick={goBack} 
          title={t('common.back') || 'Back'} 
          aria-label={t('common.back') || 'Back'}
          style={{ marginRight: 12 }}
        />
        <h1 className="department-title">
          {departmentId ? departmentName : ''}
        </h1>
        <Dropdown
          menu={{ items: menuItems }}
          trigger={['click']}
          placement="bottomRight"
          overlayStyle={{ minWidth: '120px' }}
        >
          <Button
            type="default"
            icon={<MoreOutlined />}
            className="dropdown-trigger"
            title={t('common.actions') || 'Actions'}
          />
        </Dropdown>
      </div>
      <div className="agents-list">
        {displayAgents.map((agent: Agent, idx: number) => {
          const cardId = (agent as any)?.card?.id ?? (agent as any)?.id ?? `${t('common.agent') || 'agent'}-${idx}`;
          return (
            <AgentAvatar
              key={cardId}
              agent={agent}
              onChat={() => navigate(`/chat?agentId=${cardId}`)}
            />
          );
        })}
      </div>
    </div>
  );
};

export default DepartmentRoom;