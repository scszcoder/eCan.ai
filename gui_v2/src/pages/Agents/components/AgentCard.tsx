/**
 * AgentCard Component
 * 
 * 改进：
 * 1. 改善TypeSecurity
 * 2. Optimize React.memo 比较Function
 * 3. 保持原有的Concise性
 */

import React, { useMemo, memo } from 'react';
import { App, Button, Dropdown } from 'antd';
import type { MenuProps } from 'antd';
import { MessageOutlined, MoreOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useNavigate, useLocation } from 'react-router-dom';
import { Agent, type AgentCard as AgentCardType } from '../types';
import { useAgentStore } from '@/stores/agentStore';
import { useOrgStore } from '@/stores/orgStore';
import { useUserStore } from '@/stores/userStore';
import { get_ipc_api } from '@/services/ipc_api';
import { useDeleteConfirm } from '@/components/Common/DeleteConfirmModal';
import './AgentCard.css';
import { useAvatarSceneStore } from '@/stores/avatarSceneStore';
import { avatarSceneOrchestrator } from '@/services/avatarSceneOrchestrator';

interface AgentCardProps {
  agent: Agent | AgentCardType;
  onChat?: () => void;
}

/**
 * SecurityGet Agent ID
 */
function getAgentId(agent: Agent | AgentCardType): string {
  if ('id' in agent) return agent.id;
  if ('card' in agent && agent.card?.id) return agent.card.id;
  return '';
}

/**
 * SecurityGet Agent Name
 */
function getAgentName(agent: Agent | AgentCardType): string {
  if ('name' in agent && typeof agent.name === 'string') return agent.name;
  if ('card' in agent && typeof agent.card?.name === 'string') return agent.card.name;
  return '';
}

/**
 * SecurityGet Agent Description
 */
function getAgentDescription(agent: Agent | AgentCardType): string {
  if ('description' in agent && typeof agent.description === 'string') return agent.description;
  if ('card' in agent && typeof agent.card?.description === 'string') return agent.card.description;
  return '';
}

/**
 * AgentCard Component
 */
function AgentCard({ agent, onChat }: AgentCardProps) {
  const { t } = useTranslation();
  const showDeleteConfirm = useDeleteConfirm();
  const navigate = useNavigate();
  const location = useLocation();
  const username = useUserStore((state) => state.username);
  const myTwinAgent = useAgentStore((state) => state.getMyTwinAgent());

  // SecurityGetProperty
  const id = getAgentId(agent);
  const name = getAgentName(agent);
  const description = getAgentDescription(agent);
  const myTwinAgentId = myTwinAgent?.card?.id;

  // Scene playback state
  const videoRef = React.useRef<HTMLVideoElement>(null);
  const originalSrcRef = React.useRef<string>('');
  const currentScene = useAvatarSceneStore(s => id ? s.getCurrentScene(id) : undefined);
  const isPlayingScene = Boolean(currentScene && (currentScene as any).state === 'playing');

  // GetWhen前组织ID（从URLPath中提取）
  const currentOrgId = useMemo(() => {
    const orgMatches = location.pathname.match(/organization\/([^/]+)/g);
    if (orgMatches && orgMatches.length > 0) {
      const lastMatch = orgMatches[orgMatches.length - 1];
      return lastMatch.replace('organization/', '');
    }
    return null;
  }, [location.pathname]);
  
  // Get agent 的 avatar Information（Backend保证总是返回，要么是指定的，要么是随机System头像）
  const agentAvatar = 'avatar' in agent ? agent.avatar : undefined;

  // 使用 useMemo Get媒体 URL
  const mediaUrl = useMemo<string>(() => {
    // 优先使用视频，If没有则使用图片
    if (agentAvatar?.videoExists && agentAvatar.videoPath) {
      return agentAvatar.videoPath;
    }
    if (agentAvatar?.imageUrl) {
      return agentAvatar.imageUrl;
    }
    return '';
  }, [agentAvatar?.id, agentAvatar?.videoPath, agentAvatar?.videoExists, agentAvatar?.imageUrl]);
  
  // 判断是否为视频
  const isVideo = Boolean(
    mediaUrl && 
    typeof mediaUrl === 'string' && 
    (mediaUrl.trim().toLowerCase().endsWith('.webm') || 
     mediaUrl.trim().toLowerCase().endsWith('.mp4') ||
     mediaUrl.includes('.webm') ||
     mediaUrl.includes('.mp4'))
  );

  // Handle scene playback by replacing video src
  React.useEffect(() => {
    const video = videoRef.current;
    if (!video || !id) return;

    if (isPlayingScene && currentScene) {
      // Save original src if not already saved
      if (!originalSrcRef.current) {
        const currentSrc = video.currentSrc || video.src || mediaUrl;
        if (currentSrc) {
          originalSrcRef.current = currentSrc;
          console.log('[AgentCard] Saved original src:', originalSrcRef.current);
        }
      }

      // Replace with scene clip
      const sceneUrl = currentScene.clip.clip;
      console.log('[AgentCard] Playing scene:', sceneUrl);
      video.src = sceneUrl;
      video.loop = false;
      video.currentTime = 0;
      video.play().catch(e => console.warn('[AgentCard] play rejected:', e));

      let ended = false;
      const restoreOriginal = () => {
        if (ended) return;
        ended = true;
        console.log('[AgentCard] Scene ended, restoring original');
        avatarSceneOrchestrator.onMediaEnded(id);
        if (originalSrcRef.current) {
          video.src = originalSrcRef.current;
          video.loop = true;
          video.currentTime = 0;
          video.play().catch(() => {});
        }
      };

      const onEnded = () => {
        console.log('[AgentCard] ended event fired');
        restoreOriginal();
      };
      
      const onLoadedMetadata = () => {
        const duration = video.duration;
        console.log('[AgentCard] Scene duration:', duration);
        if (isFinite(duration) && duration > 0) {
          setTimeout(() => {
            console.log('[AgentCard] Timeout fallback triggered');
            restoreOriginal();
          }, (duration + 0.5) * 1000);
        }
      };

      video.addEventListener('ended', onEnded);
      video.addEventListener('loadedmetadata', onLoadedMetadata);
      
      return () => {
        video.removeEventListener('ended', onEnded);
        video.removeEventListener('loadedmetadata', onLoadedMetadata);
      };
    } else {
      if (video && originalSrcRef.current && video.src !== originalSrcRef.current) {
        console.log('[AgentCard] Restoring to original (no scene)');
        video.src = originalSrcRef.current;
        video.loop = true;
        video.currentTime = 0;
        video.play().catch(() => {});
      }
    }
  }, [isPlayingScene, currentScene, id, mediaUrl]);
  
  // ProcessEdit
  const handleEdit = () => {
    if (!id) {
      console.error('[AgentCard] handleEdit: No agent ID found', { agent });
      return;
    }
    
    // 传递When前组织ID作为QueryParameter
    const queryParams = new URLSearchParams();
    if (currentOrgId) {
      queryParams.set('orgId', currentOrgId);
    }
    const queryString = queryParams.toString();
    const targetUrl = `/agents/details/${id}${queryString ? `?${queryString}` : ''}`;
    navigate(targetUrl);
  };
  
  // 使用 App Component的上下文
  const { message } = App.useApp();
  
  // ProcessDelete
  const handleDelete = () => {
    if (!id || !username) {
      console.error('[AgentCard] handleDelete: No agent ID or username');
      return;
    }
    
    showDeleteConfirm({
      title: t('pages.agents.deleteConfirmTitle', 'Delete Agent'),
      message: t('pages.agents.deleteConfirmMessage', `Are you sure you want to delete "${name}"? This action cannot be undone.`),
      okText: t('common.delete', 'Delete'),
      cancelText: t('common.cancel', 'Cancel'),
      onOk: async () => {
        try {
          const api = get_ipc_api();
          const res = await api.deleteAgent(username, [id]);
          
          if (res.success) {
            message.success(t('common.deleted_successfully') || 'Deleted successfully');
            
            // 从 agentStore 中Remove已Delete的 agent
            const removeAgent = useAgentStore.getState().removeAgent;
            removeAgent(id);
            
            // 同时从 orgStore 中Remove
            const removeAgentFromOrg = useOrgStore.getState().removeAgentFromOrg;
            removeAgentFromOrg(id);
            
            // Refresh组织和 agent Data以确保界面Update
            try {
              const refreshResponse = await api.getAllOrgAgents(username);
              if (refreshResponse?.success && refreshResponse.data) {
                useOrgStore.getState().setAllOrgAgents(refreshResponse.data as any);
              }
            } catch (error) {
              console.error('[AgentCard] Error refreshing org data after delete:', error);
            }
          } else {
            message.error(res.error?.message || (t('common.delete_failed') as string) || 'Delete failed');
          }
        } catch (e: any) {
          message.error(e?.message || t('common.delete_failed') || 'Delete failed');
        }
      }
    });
  };
  
  // Menu项
  const menuItems: MenuProps['items'] = [
    { key: 'edit', label: t('common.edit') || 'Edit', onClick: handleEdit },
    { key: 'delete', label: t('common.delete') || 'Delete', onClick: handleDelete, danger: true },
  ];
  
  return (
    <div className="agent-card" style={{ position: 'relative' }}>
      {/* 媒体Content */}
      <div style={{ position: 'relative', width: 300, height: 169, marginBottom: 26 }}>
        {isVideo ? (
          <div
            className="agent-gif-video-wrapper"
            style={{
              position: 'absolute',
              inset: 0,
              borderRadius: 28,
              background: '#222c',
              border: '4px solid var(--primary-color, #3b82f6)',
              boxShadow: '0 4px 18px 0 rgba(59,130,246,0.13)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              overflow: 'hidden'
            }}
          >
            <video
              ref={videoRef}
              src={mediaUrl}
              className="agent-gif agent-gif-video"
              autoPlay
              loop
              muted
              playsInline
              preload="metadata"
              width={300}
              height={169}
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'contain',
                borderRadius: 28,
                background: 'transparent'
              }}
            />
          </div>
        ) : (
          <img
            src={mediaUrl}
            alt={t('common.agent_working') || 'agent working'}
            className="agent-gif"
            loading="lazy"
            style={{
              position: 'absolute',
              inset: 0,
              width: '100%',
              height: '100%',
              objectFit: 'contain',
              borderRadius: 28,
              background: '#222c',
              border: '4px solid var(--primary-color, #3b82f6)',
              boxShadow: '0 4px 18px 0 rgba(59,130,246,0.13)'
            }}
            onError={() => {
              if (process.env.NODE_ENV === 'development') {
                console.error('[AgentCard] Image load error:', {
                  agentId: id,
                  agentName: name,
                  mediaUrl,
                  agentAvatar
                });
              }
            }}
          />
        )}
      </div>
      
      {/* Information行 */}
      <div
        className="agent-info-row"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12
        }}
      >
        <span style={{ display: 'inline-flex', alignItems: 'center' }}>
          <Dropdown menu={{ items: menuItems }} trigger={["click"]} placement="bottomLeft">
            <Button shape="circle" icon={<MoreOutlined />} size="middle" />
          </Dropdown>
        </span>
        
        <div className="agent-name" style={{ flex: 1, textAlign: 'center' }}>
          {name ? t(name) : ''}
        </div>
        
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
      
      {/* Description */}
      {description && (
        <div className="agent-desc">{t(description)}</div>
      )}
    </div>
  );
}

/**
 * 使用 React.memo OptimizePerformance，避免不必要的重Render
 * Custom比较Function：只在 agent ID 或关键Property变化时重新Render
 */
export default memo(AgentCard, (prevProps, nextProps) => {
  const prevId = getAgentId(prevProps.agent);
  const nextId = getAgentId(nextProps.agent);
  const prevName = getAgentName(prevProps.agent);
  const nextName = getAgentName(nextProps.agent);
  
  // If ID 或Name变化，Need重新Render
  if (prevId !== nextId || prevName !== nextName) {
    return false;
  }
  
  // Check avatar 是否变化
  const prevAvatar = 'avatar' in prevProps.agent ? prevProps.agent.avatar : undefined;
  const nextAvatar = 'avatar' in nextProps.agent ? nextProps.agent.avatar : undefined;
  if (prevAvatar?.id !== nextAvatar?.id) {
    return false;
  }
  
  // onChat Callback变化不Trigger重Render（通常是Stable的）
  return true;
});
