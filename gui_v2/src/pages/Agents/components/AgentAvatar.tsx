import React, { useMemo, useRef } from 'react';
import agentGifs from '@/assets/gifs'; // 需实现导入所有 gif
import { Agent, AgentCard } from '../types';
import './AgentAvatar.css';
import { Button } from 'antd';
import { MessageOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useAppDataStore } from '@/stores/appDataStore';

function getRandomGif(): string {
  // 这里假设 agentGifs 是一个字符串数组
  const idx = Math.floor(Math.random() * agentGifs.length);
  return agentGifs[idx] as string;
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
  const mediaUrl = useMemo<string>(() => getRandomGif(), []);
  // 只要 mediaUrl 存在且以 .webm 或 .mp4 结尾就用 video
  const isVideo = Boolean(mediaUrl && typeof mediaUrl === 'string' && (mediaUrl.trim().toLowerCase().endsWith('.webm') || mediaUrl.trim().toLowerCase().endsWith('.mp4')));
  const [error, setError] = React.useState(false);

  // render 次数日志
  const renderCount = useRef(0);
  renderCount.current++;
  // console.log('AgentAvatar render', id, 'count:', renderCount.current, agent);

  console.log('is video', isVideo, ' gif url:', mediaUrl);
  // console.log('agentGifs:', agentGifs);

  return (
    <div className="agent-avatar" key={id}>
      {isVideo ? (
        <div
          className="agent-gif-video-wrapper"
          style={{ width: 300, height: 300 * 9 / 16, marginBottom: 26, borderRadius: 28, background: '#222c', border: '4px solid var(--primary-color, #3b82f6)', boxShadow: '0 4px 18px 0 rgba(59,130,246,0.13)', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}
        >
          <video
            src={mediaUrl}
            className="agent-gif agent-gif-video"
            autoPlay
            loop
            muted
            playsInline
            width={300}
            height={300 * 9 / 16}
            style={{ width: '100%', height: '100%', objectFit: 'contain', borderRadius: 28, background: 'transparent' }}
            poster="/default-agent-poster.png"
            // onError={e => { console.error('video load error', mediaUrl, e); setError(true); }}
          />
        </div>
      ) : (
        <img src={mediaUrl} alt="agent working" className="agent-gif" style={{ width: 300, height: 300 * 9 / 16, objectFit: 'contain', borderRadius: 28, marginBottom: 26, background: '#222c', border: '4px solid var(--primary-color, #3b82f6)', boxShadow: '0 4px 18px 0 rgba(59,130,246,0.13)' }} onError={e => { console.error('img load error', mediaUrl, e); setError(true); }} />
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