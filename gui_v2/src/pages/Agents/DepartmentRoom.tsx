import React, { useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, Dropdown, Space } from 'antd';
import { PlusOutlined, MoreOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import type { MenuProps } from 'antd';
import { useAppDataStore } from '../../stores/appDataStore';
import AgentAvatar from './components/AgentAvatar';
import './DepartmentRoom.css';
import { Agent } from './types';
import departments from './data/departments';
import { useTranslation } from 'react-i18next';

const DepartmentRoom: React.FC = () => {
  const { departmentId } = useParams<{ departmentId: string }>();
  const navigate = useNavigate();
  const agents = useAppDataStore((state) => state.agents);
  const { t } = useTranslation();

  // 返回 doors 列表，使用 replace 避免页面闪烁
  const goBack = useCallback(() => {
    navigate('/agents', { replace: true }); // Navigate to parent route
  }, [navigate]);

  // 过滤当前部门的agent，如果没有匹配则显示全部
  let deptAgents = agents.filter((a: Agent) => {
    // 兼容card和旧结构
    const dept = (a as any).departmentId || a.organizations?.[0];
    return departmentId ? dept === departmentId : true;
  });
  if (deptAgents.length === 0) deptAgents = agents;

  // 获取当前部门的国际化名称
  let departmentName = '';
  if (departmentId) {
    const dept = departments.find(d => d.id === departmentId);
    departmentName = dept ? t(dept.name) : departmentId;
  }

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
        {deptAgents.map((agent: Agent, idx: number) => {
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