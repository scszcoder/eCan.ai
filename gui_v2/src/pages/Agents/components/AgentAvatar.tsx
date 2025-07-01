import React from 'react';
import agentGifs from '@/assets/gifs'; // 需实现导入所有 gif
import { Agent, AgentCard } from '../types';
import './AgentAvatar.css';
import { Button, Tooltip } from 'antd';
import { MessageOutlined } from '@ant-design/icons';

function getRandomGif() {
  // 这里假设 agentGifs 是一个字符串数组
  const idx = Math.floor(Math.random() * agentGifs.length);
  return agentGifs[idx];
}

interface AgentAvatarProps {
  agent: Agent | AgentCard;
  onChat?: () => void;
}

const AgentAvatar: React.FC<AgentAvatarProps> = ({ agent, onChat }) => {
  // 兼容Agent和AgentCard
  const name = (agent as any).name || (agent as any).card?.name;
  const desc = (agent as any).description || (agent as any).card?.description;
  const gif = getRandomGif();
  const isVideo = gif.endsWith('.mp4');

  console.log('gif url:', gif);

  return (
    <div className="agent-avatar">
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
        <div className="agent-name">{name}</div>
        <Tooltip title="Chat">
          <Button
            type="primary"
            shape="circle"
            icon={<MessageOutlined />}
            size="large"
            className="agent-chat-btn"
            onClick={onChat}
          />
        </Tooltip>
      </div>
      {desc && <div className="agent-desc">{desc}</div>}
    </div>
  );
};

export default AgentAvatar; 