import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAppDataStore } from '../../stores/appDataStore';
import AgentAvatar from './components/AgentAvatar';
import './DepartmentRoom.css';
import { Agent } from './types';

const DepartmentRoom: React.FC = () => {
  const { departmentId } = useParams<{ departmentId: string }>();
  const navigate = useNavigate();
  const agents = useAppDataStore((state) => state.agents);

  // 过滤当前部门的agent，如果没有匹配则显示全部
  let deptAgents = agents.filter((a: Agent) => {
    // 兼容card和旧结构
    const dept = (a as any).departmentId || a.organizations?.[0];
    return departmentId ? dept === departmentId : true;
  });
  if (deptAgents.length === 0) deptAgents = agents;

  return (
    <div className="department-room">
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