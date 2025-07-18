import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
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

  return (
    <div className="department-room">
      {departmentId && (
        <div style={{ fontSize: 28, fontWeight: 700, color: '#fff', margin: '32px 0 0 0', textAlign: 'center', letterSpacing: 1, textShadow: '0 2px 8px #0008' }}>
          {departmentName}
        </div>
      )}
      <div className="agents-list">
        {deptAgents.map((agent: Agent) => (
          <AgentAvatar
            key={agent.card.id}
            agent={agent}
            onChat={() => navigate(`/chat?agentId=${agent.card.id}`)}
          />
        ))}
      </div>
    </div>
  );
};

export default DepartmentRoom; 