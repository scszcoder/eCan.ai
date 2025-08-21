import React, { useMemo, useRef, useEffect } from 'react';
import agentGifs, { logVideoSupport } from '@/assets/gifs'; // 需实现导入所有 gif
import { Agent, AgentCard } from '../types';
import { Button, Dropdown, Modal, message } from 'antd';
import type { MenuProps } from 'antd';
import { MessageOutlined, MoreOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useAppDataStore } from '@/stores/appDataStore';
import { useNavigate } from 'react-router-dom';
import { useUserStore } from '@/stores/userStore';
import { get_ipc_api } from '@/services/ipc_api';

function getRandomGif(): string {
  // 这里假设 agentGifs 是一个字符串数组
  if (!Array.isArray(agentGifs) || agentGifs.length === 0) return '';
  const idx = Math.floor(Math.random() * agentGifs.length);
  return agentGifs[idx] as string;
}

// 全局标记，确保视频支持检测只执行一次
let videoSupportChecked = false;

interface AgentAvatarProps {
  agent: Agent | AgentCard;
  onChat?: () => void;
}

function AgentAvatar({ agent, onChat }: AgentAvatarProps) {
  const { t } = useTranslation();
  const myTwinAgent = useAppDataStore((state: any) => state.myTwinAgent());
  const myTwinAgentId = myTwinAgent?.card?.id;
  const navigate = useNavigate();
  const username = useUserStore((s: any) => s.username);
  // 兼容Agent和AgentCard
  const id = (agent as any).id || (agent as any).card?.id;
  const rawName = (agent as any).name ?? (agent as any).card?.name;
  const rawDesc = (agent as any).description ?? (agent as any).card?.description;
  const safeName = typeof rawName === 'string' ? rawName : '';
  const safeDesc = typeof rawDesc === 'string' ? rawDesc : '';
  const mediaUrl = useMemo<string>(() => getRandomGif(), []);

  // 只要 mediaUrl 存在且以 .webm 或 .mp4 结尾就用 video
  const isVideo = Boolean(mediaUrl && typeof mediaUrl === 'string' && (mediaUrl.trim().toLowerCase().endsWith('.webm') || mediaUrl.trim().toLowerCase().endsWith('.mp4')));
  const [error, setError] = React.useState(false);

  // render 次数日志
  const renderCount = useRef(0);
  renderCount.current++;
  // console.log('AgentAvatar render', id, 'count:', renderCount.current, agent);

  // 在第一次渲染时检测视频支持
  useEffect(() => {
    if (!videoSupportChecked) {
      videoSupportChecked = true;
      logVideoSupport();
    }
  }, []);

  console.log('is video', isVideo, ' gif url:', mediaUrl);
  // console.log('agentGifs:', agentGifs);

  const handleEdit = () => {
    if (!id) return;
    navigate(`/agents/details/${id}`);
  };

  const handleDelete = () => {
    if (!id) return;
    Modal.confirm({
      title: t('common.confirm_delete') || 'Confirm Delete',
      content: t('common.confirm_delete_desc') || 'Are you sure you want to delete this agent?',
      okText: t('common.ok') || 'OK',
      cancelText: t('common.cancel') || 'Cancel',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          const api = get_ipc_api();
          const res = await api.deleteAgent(username, id);
          if (res.success) {
            message.success(t('common.deleted_successfully') || 'Deleted successfully');
          } else {
            message.error(res.error?.message || (t('common.delete_failed') as string) || 'Delete failed');
          }
        } catch (e: any) {
          message.error(e?.message || 'Delete failed');
        }
      }
    });
  };

  const menuItems: MenuProps['items'] = [
    { key: 'edit', label: t('common.edit') || 'Edit', onClick: handleEdit },
    { type: 'divider' },
    { key: 'delete', label: t('common.delete') || 'Delete', danger: true, onClick: handleDelete },
  ];

  return (
    <div className="agent-avatar" key={id} style={{ position: 'relative' }}>
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
            poster="./assets/default-agent-poster.png"
            // onError={e => { console.error('video load error', mediaUrl, e); setError(true); }}
          />
        </div>
      ) : (
        <img src={mediaUrl} alt="agent working" className="agent-gif" style={{ width: 300, height: 300 * 9 / 16, objectFit: 'contain', borderRadius: 28, marginBottom: 26, background: '#222c', border: '4px solid var(--primary-color, #3b82f6)', boxShadow: '0 4px 18px 0 rgba(59,130,246,0.13)' }} onError={e => { console.error('img load error', mediaUrl, e); setError(true); }} />
      )}
      <div className="agent-info-row" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
        <span style={{ display: 'inline-flex', alignItems: 'center' }}>
          <Dropdown menu={{ items: menuItems }} trigger={["click"]} placement="bottomLeft">
            <Button shape="circle" icon={<MoreOutlined />} size="middle" />
          </Dropdown>
        </span>
        <div className="agent-name" style={{ flex: 1, textAlign: 'center' }}>{safeName ? t(safeName) : ''}</div>
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

      {safeDesc && <div className="agent-desc">{t(safeDesc)}</div>}
    </div>
  );
}

export default React.memo(AgentAvatar);