import React, { useMemo, useRef } from 'react';
import agentGifs from '@/assets/gifs'; // 需实现导入所有 gif
import { Agent, AgentCard } from '../types';
import './AgentAvatar.css';
import { Button, Tooltip } from 'antd';
import { MessageOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useAppDataStore } from '@/stores/appDataStore';

function getRandomGif() {
  // 这里假设 agentGifs 是一个字符串数组
  const idx = Math.floor(Math.random() * agentGifs.length);
  return agentGifs[idx];
}

interface AgentAvatarProps {
  agent: Agent | AgentCard;
  onChat?: () => void;
}

function AgentAvatar({ agent, onChat }: AgentAvatarProps) {
  const { t } = useTranslation();
  const myTwinAgent = useAppDataStore((state: any) => state.myTwinAgent());
  const myTwinAgentId = myTwinAgent?.card?.id;
  // 兼容Agent和AgentCard
  const id = (agent as any).id || (agent as any).card?.id;
  const name = (agent as any).name || (agent as any).card?.name;
  const desc = (agent as any).description || (agent as any).card?.description;
  const gif = useMemo(() => getRandomGif(), []);
  const isVideo = gif.endsWith('.mp4');

  // render 次数日志
  const renderCount = useRef(0);
  renderCount.current++;
  console.log('AgentAvatar render', id, 'count:', renderCount.current, agent);

  console.log('gif url:', gif);

  return (
    <div className="agent-avatar" key={id}>
      {isVideo ? (
        <video
          src={gif}
          className="agent-gif"
          autoPlay
          loop
          muted
          playsInline
        />
      ) : (
        <img src={gif} alt="agent working" className="agent-gif" />
      )}
      <div className="agent-info-row">
        <div className="agent-name">{t(name)}</div>
        <span style={{ display: 'inline-block' }}>
          <Button
            type="primary"
            shape="circle"
            icon={<MessageOutlined />}
            size="large"
            className="agent-chat-btn"
            onClick={onChat}
            disabled={id === myTwinAgentId}
          />
        </span>
      </div>
      {desc && <div className="agent-desc">{t(desc)}</div>}
    </div>
  );
}

export default React.memo(AgentAvatar); 