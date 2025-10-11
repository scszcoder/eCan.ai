/**
 * AgentCard 组件
 * 
 * 改进：
 * 1. 改善类型安全
 * 2. 优化 React.memo 比较函数
 * 3. 保持原有的简洁性
 */

import React, { useMemo, useEffect } from 'react';
import { App, Button, Dropdown } from 'antd';
import type { MenuProps } from 'antd';
import { MessageOutlined, MoreOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useNavigate, useLocation } from 'react-router-dom';
import agentGifs, { logVideoSupport } from '@/assets/gifs';
import { Agent, type AgentCard as AgentCardType } from '../types';
import { useAgentStore } from '@/stores/agentStore';
import { useOrgStore } from '@/stores/orgStore';
import { useUserStore } from '@/stores/userStore';
import { get_ipc_api } from '@/services/ipc_api';
import './AgentCard.css';

// 全局标记，确保视频支持检测只执行一次
let videoSupportChecked = false;

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
  
  // 使用 useMemo 获取固定的媒体 URL（基于 ID）
  const mediaUrl = useMemo<string>(() => {
    if (!id || !Array.isArray(agentGifs) || agentGifs.length === 0) {
      return Array.isArray(agentGifs) && agentGifs.length > 0 
        ? agentGifs[Math.floor(Math.random() * agentGifs.length)] as string 
        : '';
    }
    // 使用 agent ID 作为种子生成固定的随机数
    const seed = id.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
    const index = seed % agentGifs.length;
    return agentGifs[index] as string;
  }, [id]);
  
  // 判断是否为视频
  const isVideo = Boolean(
    mediaUrl && 
    typeof mediaUrl === 'string' && 
    (mediaUrl.trim().toLowerCase().endsWith('.webm') || 
     mediaUrl.trim().toLowerCase().endsWith('.mp4'))
  );
  
  // 在第一次渲染时检测视频支持
  useEffect(() => {
    if (!videoSupportChecked) {
      videoSupportChecked = true;
      logVideoSupport();
    }
  }, []);
  
  // 处理编辑
  const handleEdit = () => {
    if (!id) {
      console.error('[AgentCard] handleEdit: No agent ID found', { agent });
      return;
    }
    console.log('[AgentCard] handleEdit called for agent:', { id, name, agent });
    
    // 传递当前组织ID作为查询参数
    const queryParams = new URLSearchParams();
    if (currentOrgId && currentOrgId !== 'root' && currentOrgId !== 'unassigned') {
      queryParams.set('orgId', currentOrgId);
    }
    const queryString = queryParams.toString();
    const targetUrl = `/agents/details/${id}${queryString ? `?${queryString}` : ''}`;
    console.log('[AgentCard] Navigating to edit:', { 
      agentId: id, 
      agentName: name,
      currentOrgId, 
      targetUrl 
    });
    navigate(targetUrl);
  };
  
  // 使用 App 组件的上下文
  const { modal, message } = App.useApp();
  
  // 处理删除
  const handleDelete = () => {
    if (!id || !username) {
      console.error('[AgentCard] handleDelete: No agent ID or username');
      return;
    }
    
    modal.confirm({
      title: t('common.confirm_delete') || 'Confirm Delete',
      content: t('common.confirm_delete_desc') || 'Are you sure you want to delete this agent?',
      okText: t('common.ok') || 'OK',
      cancelText: t('common.cancel') || 'Cancel',
      okButtonProps: { danger: true },
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
            width={300}
            height={169}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'contain',
              borderRadius: 28,
              background: 'transparent'
            }}
            poster="./assets/default-agent-poster.png"
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
          onError={(e) => console.error(t('common.img_load_error') || 'img load error', mediaUrl, e)}
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
 * 优化的 memo 比较函数
 * 只在 agent.id 变化时重新渲染
 */
export default React.memo(AgentCard, (prevProps, nextProps) => {
  const prevId = getAgentId(prevProps.agent);
  const nextId = getAgentId(nextProps.agent);
  
  // 如果 ID 相同且 onChat 函数相同，则不重新渲染
  return prevId === nextId && prevProps.onChat === nextProps.onChat;
});
