/**
 * AgentCard 组件
 * 
 * 改进：
 * 1. 改善类型安全
 * 2. 优化 React.memo 比较函数
 * 3. 保持原有的简洁性
 */

import { useMemo, memo } from 'react';
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

interface AgentCardProps {
  agent: Agent | AgentCardType;
  onChat?: () => void;
}

/**
 * 安全获取 Agent ID
 */
function getAgentId(agent: Agent | AgentCardType): string {
  if ('id' in agent) return agent.id;
  if ('card' in agent && agent.card?.id) return agent.card.id;
  return '';
}

/**
 * 安全获取 Agent 名称
 */
function getAgentName(agent: Agent | AgentCardType): string {
  if ('name' in agent && typeof agent.name === 'string') return agent.name;
  if ('card' in agent && typeof agent.card?.name === 'string') return agent.card.name;
  return '';
}

/**
 * 安全获取 Agent 描述
 */
function getAgentDescription(agent: Agent | AgentCardType): string {
  if ('description' in agent && typeof agent.description === 'string') return agent.description;
  if ('card' in agent && typeof agent.card?.description === 'string') return agent.card.description;
  return '';
}

/**
 * AgentCard 组件
 */
function AgentCard({ agent, onChat }: AgentCardProps) {
  const { t } = useTranslation();
  const showDeleteConfirm = useDeleteConfirm();
  const navigate = useNavigate();
  const location = useLocation();
  const username = useUserStore((state) => state.username);
  const myTwinAgent = useAgentStore((state) => state.getMyTwinAgent());

  // 安全获取属性
  const id = getAgentId(agent);
  const name = getAgentName(agent);
  const description = getAgentDescription(agent);
  const myTwinAgentId = myTwinAgent?.card?.id;

  // 获取当前组织ID（从URL路径中提取）
  const currentOrgId = useMemo(() => {
    const orgMatches = location.pathname.match(/organization\/([^/]+)/g);
    if (orgMatches && orgMatches.length > 0) {
      const lastMatch = orgMatches[orgMatches.length - 1];
      return lastMatch.replace('organization/', '');
    }
    return null;
  }, [location.pathname]);
  
  // 获取 agent 的 avatar 信息（后端保证总是返回，要么是指定的，要么是随机系统头像）
  const agentAvatar = 'avatar' in agent ? agent.avatar : undefined;

  // 使用 useMemo 获取媒体 URL
  const mediaUrl = useMemo<string>(() => {
    // 优先使用视频，如果没有则使用图片
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
  
  // 处理编辑
  const handleEdit = () => {
    if (!id) {
      console.error('[AgentCard] handleEdit: No agent ID found', { agent });
      return;
    }
    
    // 传递当前组织ID作为查询参数
    const queryParams = new URLSearchParams();
    if (currentOrgId) {
      queryParams.set('orgId', currentOrgId);
    }
    const queryString = queryParams.toString();
    const targetUrl = `/agents/details/${id}${queryString ? `?${queryString}` : ''}`;
    navigate(targetUrl);
  };
  
  // 使用 App 组件的上下文
  const { message } = App.useApp();
  
  // 处理删除
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
            
            // 从 agentStore 中移除已删除的 agent
            const removeAgent = useAgentStore.getState().removeAgent;
            removeAgent(id);
            
            // 同时从 orgStore 中移除
            const removeAgentFromOrg = useOrgStore.getState().removeAgentFromOrg;
            removeAgentFromOrg(id);
            
            // 刷新组织和 agent 数据以确保界面更新
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
  
  // 菜单项
  const menuItems: MenuProps['items'] = [
    { key: 'edit', label: t('common.edit') || 'Edit', onClick: handleEdit },
    { key: 'delete', label: t('common.delete') || 'Delete', onClick: handleDelete, danger: true },
  ];
  
  return (
    <div className="agent-card" style={{ position: 'relative' }}>
      {/* 媒体内容 */}
      {isVideo ? (
        <div
          className="agent-gif-video-wrapper"
          style={{
            width: 300,
            height: 169,
            marginBottom: 26,
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
              background: 'transparent',
              transform: 'translate3d(0, 0, 0)', // 触发GPU硬件加速
              willChange: 'transform', // 提示浏览器优化
              backfaceVisibility: 'hidden', // 优化渲染性能
              WebkitBackfaceVisibility: 'hidden' // Safari兼容
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
            width: 300,
            height: 169,
            objectFit: 'contain',
            borderRadius: 28,
            marginBottom: 26,
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
      
      {/* 信息行 */}
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
      
      {/* 描述 */}
      {description && (
        <div className="agent-desc">{t(description)}</div>
      )}
    </div>
  );
}

/**
 * 使用 React.memo 优化性能，避免不必要的重渲染
 * 自定义比较函数：只在 agent ID 或关键属性变化时重新渲染
 */
export default memo(AgentCard, (prevProps, nextProps) => {
  const prevId = getAgentId(prevProps.agent);
  const nextId = getAgentId(nextProps.agent);
  const prevName = getAgentName(prevProps.agent);
  const nextName = getAgentName(nextProps.agent);
  
  // 如果 ID 或名称变化，需要重新渲染
  if (prevId !== nextId || prevName !== nextName) {
    return false;
  }
  
  // 检查 avatar 是否变化
  const prevAvatar = 'avatar' in prevProps.agent ? prevProps.agent.avatar : undefined;
  const nextAvatar = 'avatar' in nextProps.agent ? nextProps.agent.avatar : undefined;
  if (prevAvatar?.id !== nextAvatar?.id) {
    return false;
  }
  
  // onChat 回调变化不触发重渲染（通常是稳定的）
  return true;
});
