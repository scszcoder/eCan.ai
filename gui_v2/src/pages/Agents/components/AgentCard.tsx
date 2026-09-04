/**
 * AgentCard Component
 * 
 * 改进：
 * 1. 改善TypeSecurity
 * 2. Optimize React.memo 比较Function
 * 3. 保持原有的Concise性
 */

import React, { useMemo, memo, useState, useEffect, useCallback } from 'react';
import { App, Badge, Button, Dropdown, Popover, Tooltip, Tag, Spin, Empty } from 'antd';
import type { MenuProps } from 'antd';
import { MessageOutlined, MoreOutlined, PoweroffOutlined, UnorderedListOutlined } from '@ant-design/icons';
import { useTaskStore } from '@/stores/domain/taskStore';
import { useTranslation } from 'react-i18next';
import { useNavigate, useLocation } from 'react-router-dom';
import { Agent, type AgentCard as AgentCardType } from '../types';
import { useAgentStore } from '@/stores/agentStore';
import { useOrgStore } from '@/stores/orgStore';
import { useUserStore } from '@/stores/userStore';
import { get_ipc_api } from '@/services/ipc_api';
import { ipcApi } from '@/services/ipc/api';
import { useAgentRuntimeStore, type RuntimeStatus } from '@/stores/agentRuntimeStore';
import { useDeleteConfirm } from '@/components/Common/DeleteConfirmModal';
import './AgentCard.css';
import { useAvatarSceneStore } from '@/stores/avatarSceneStore';
import { eventBus } from '@/utils/eventBus';
import { avatarSceneOrchestrator } from '@/services/avatarSceneOrchestrator';
import { useEffectOnActive } from 'keepalive-for-react';
import { AgentHostTag } from './AgentHostTag';
import { ReadinessStrip } from './ReadinessStrip';

// DEPRECATED: My Twin Agent related code - kept for reference, will be removed later
// Previously: const myTwinAgent = useAgentStore(state => state.getMyTwinAgent());
// Previously: const myTwinAgentId = myTwinAgent?.card?.id;
// Previously: Chat button was disabled when agent.card?.id === myTwinAgentId
// Now: Chat button is always enabled for all agents

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
 * Task status display helper
 */
function getTaskStatusDisplay(task: any): { label: string; color: string } {
  // Prioritize live status from IPC events, then state.top (runtime), then DB status
  const liveStatus = task?._liveStatus;
  const stateTop = task?.state?.top || task?.metadata?.state?.top;
  const status = liveStatus || stateTop || task?.status || 'pending';
  const s = String(status).toLowerCase();

  // Terminal states take priority
  if (s === 'completed' || s === 'done') return { label: 'Completed', color: 'success' };
  if (s === 'failed' || s === 'error') return { label: 'Failed', color: 'error' };
  if (s === 'cancelled') return { label: 'Cancelled', color: 'default' };

  // Explicit running
  if (s === 'running' || s === 'in_progress') return { label: 'Running', color: 'processing' };

  // Infer running from trigger type: auto-triggered tasks that aren't terminal are running
  const trigger = task?.trigger || '';
  const triggers = Array.isArray(trigger) ? trigger : String(trigger).split(',').map((t: string) => t.trim());
  if (triggers.includes('auto')) return { label: 'Running', color: 'processing' };

  if (s === 'scheduled' || s === 'ready') return { label: 'Scheduled', color: 'warning' };
  if (s === 'pending') return { label: 'Standby', color: 'warning' };
  return { label: status, color: 'default' };
}

/**
 * AgentTasksButton — icon button with popover listing tasks assigned to this agent
 */
function AgentTasksButton({ agentId }: { agentId: string }) {
  const { t } = useTranslation();
  const username = useUserStore((state) => state.username);
  const allTasks = useTaskStore((state) => state.items);
  const [agentTasks, setAgentTasks] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [fetched, setFetched] = useState(false);

  const fetchTasks = useCallback(async () => {
    if (!agentId || !username || fetched) return;
    setLoading(true);
    try {
      const api = get_ipc_api();

      // Step 1: ensure we have tasks loaded (fetch from API if store is empty)
      let tasks = allTasks;
      if (!tasks || tasks.length === 0) {
        try {
          const tasksResp = await api.getAgentTasks(username, []);
          if (tasksResp.success && tasksResp.data) {
            const data = tasksResp.data as any;
            tasks = Array.isArray(data) ? data : (data.tasks || []);
          }
        } catch (e) {
          console.warn('[AgentTasksButton] Failed to fetch all tasks:', e);
        }
      }

      // Step 2: try direct agentId match on tasks
      const fromStore = tasks.filter((t: any) => t.agentId === agentId || t.agent_id === agentId);
      if (fromStore.length > 0) {
        setAgentTasks(fromStore);
        setFetched(true);
        setLoading(false);
        return;
      }

      // Step 3: query agent_task_rels table and cross-reference
      const relsResp = await api.queryAgentTaskRels({ agent_id: agentId, limit: 100, offset: 0 });
      if (relsResp.success && Array.isArray(relsResp.data) && relsResp.data.length > 0) {
        const taskIds = new Set(relsResp.data.map((r: any) => String(r.task_id || '').trim()).filter(Boolean));
        const matched = tasks.filter((t: any) => taskIds.has(t.id));
        setAgentTasks(matched);
      } else {
        setAgentTasks([]);
      }
    } catch (e) {
      console.warn('[AgentTasksButton] Failed to fetch tasks:', e);
      setAgentTasks([]);
    } finally {
      setLoading(false);
      setFetched(true);
    }
  }, [agentId, username, allTasks, fetched]);

  // Listen for real-time task status updates via IPC event bus
  useEffect(() => {
    const handler = (data: any) => {
      if (!data) return;
      const taskId = data?.langgraphState?.task_id || data?.task_id;
      const taskStatus = data?.langgraphState?.task_status || data?.status;
      if (!taskId || !taskStatus) return;

      setAgentTasks((prev) => {
        const idx = prev.findIndex((t: any) => t.id === taskId || t.run_id === data.agentTaskId);
        if (idx === -1) return prev;
        const updated = [...prev];
        updated[idx] = { ...updated[idx], _liveStatus: taskStatus };
        return updated;
      });
    };
    eventBus.on('ws:update_skill_run_stat', handler);
    return () => { eventBus.off('ws:update_skill_run_stat', handler); };
  }, []);

  const handleOpenChange = (open: boolean) => {
    if (open && !fetched) {
      fetchTasks();
    }
  };

  const content = (
    <div style={{ minWidth: 200, maxWidth: 300 }}>
      {loading ? (
        <div style={{ textAlign: 'center', padding: '16px 0' }}>
          <Spin size="small" />
        </div>
      ) : agentTasks.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={
            <span style={{ color: 'rgba(255,255,255,0.45)', fontSize: 13 }}>
              {t('pages.agents.noTaskAssigned') || 'No Task Assigned'}
            </span>
          }
          style={{ margin: '8px 0' }}
        />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {agentTasks.map((task: any) => {
            const { label, color } = getTaskStatusDisplay(task);
            return (
              <div
                key={task.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 8,
                  padding: '4px 0',
                  borderBottom: '1px solid rgba(255,255,255,0.06)',
                }}
              >
                <span
                  style={{
                    fontSize: 13,
                    color: 'rgba(255,255,255,0.85)',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    flex: 1,
                  }}
                  title={task.name || task.id}
                >
                  {task.name || task.id}
                </span>
                <Tag
                  color={color}
                  style={{ margin: 0, fontSize: 11, lineHeight: '18px', flexShrink: 0 }}
                >
                  {label}
                </Tag>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );

  return (
    <Popover
      content={content}
      title={
        <span style={{ fontSize: 13, fontWeight: 600 }}>
          {t('pages.agents.tasks') || 'Tasks'}
        </span>
      }
      trigger="click"
      placement="bottom"
      onOpenChange={handleOpenChange}
    >
      <Tooltip title={t('pages.agents.tasks') || 'Tasks'}>
        <Button
          shape="circle"
          icon={<UnorderedListOutlined />}
          size="small"
          onClick={(e) => e.stopPropagation()}
          style={{
            background: 'rgba(255, 255, 255, 0.05)',
            borderColor: 'rgba(255, 255, 255, 0.1)',
            color: 'rgba(255, 255, 255, 0.7)',
            flexShrink: 0,
          }}
        />
      </Tooltip>
    </Popover>
  );
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

  const { message: messageApi, modal } = App.useApp();

  // SecurityGetProperty
  const id = getAgentId(agent);
  const name = getAgentName(agent);
  // Agent runtime status from shared store (batch-polled)
  const runtimeInfo = useAgentRuntimeStore(s => id ? s.statusMap[id] : undefined);
  const setStatus = useAgentRuntimeStore(s => s.setStatus);
  const runtimeStatus: RuntimeStatus = runtimeInfo?.runtime_status ?? 'stopped';
  const agentEnabled = runtimeInfo?.enabled ?? true;

  // Start/Stop agent
  const handleToggleAgent = useCallback(async (enable: boolean) => {
    if (!id) return;
    if (!enable) {
      modal.confirm({
        title: <span style={{ color: '#fff' }}>Stop Agent</span>,
        content: <span style={{ color: 'rgba(255,255,255,0.85)' }}>All running tasks on this agent will be shut off immediately. Are you sure?</span>,
        okText: 'Stop',
        okButtonProps: { danger: true },
        cancelText: 'Cancel',
        centered: true,
        onOk: async () => {
          try {
            const res = await ipcApi.toggleAgentEnabled<{ runtime_status: string }>(id, false);
            if (res.success && res.data) {
              setStatus(id, res.data.runtime_status as RuntimeStatus, true);
              messageApi.success('Agent stopped');
            } else {
              messageApi.error(res.error?.message || 'Failed to stop agent');
            }
          } catch (_) {
            messageApi.error('Failed to stop agent');
          }
        },
      });
    } else {
      try {
        const res = await ipcApi.toggleAgentEnabled<{ runtime_status: string }>(id, true);
        if (res.success && res.data) {
          setStatus(id, res.data.runtime_status as RuntimeStatus, true);
          messageApi.success('Agent started');
        } else {
          messageApi.error(res.error?.message || 'Failed to start agent');
        }
      } catch (_) {
        messageApi.error('Failed to start agent');
      }
    }
  }, [id, messageApi, modal, setStatus]);

  // Enable/Disable agent (persistent)
  const handleSetAgentEnabled = useCallback(async (enabled: boolean) => {
    if (!id) return;
    if (!enabled) {
      modal.confirm({
        title: <span style={{ color: '#fff' }}>Disable Agent</span>,
        content: <span style={{ color: 'rgba(255,255,255,0.85)' }}>Disabling this agent will stop all running tasks and prevent it from auto-starting when you reopen the app. Continue?</span>,
        okText: 'Disable',
        okButtonProps: { danger: true },
        cancelText: 'Cancel',
        centered: true,
        onOk: async () => {
          try {
            const res = await ipcApi.setAgentEnabled<{ enabled: boolean; runtime_status: string }>(id, false);
            if (res.success && res.data) {
              setStatus(id, res.data.runtime_status as RuntimeStatus, res.data.enabled);
              messageApi.success('Agent disabled');
            } else {
              messageApi.error(res.error?.message || 'Failed to disable agent');
            }
          } catch (_) {
            messageApi.error('Failed to disable agent');
          }
        },
      });
    } else {
      try {
        const res = await ipcApi.setAgentEnabled<{ enabled: boolean; runtime_status: string }>(id, true);
        if (res.success && res.data) {
          setStatus(id, res.data.runtime_status as RuntimeStatus, res.data.enabled);
          messageApi.success('Agent enabled');
        } else {
          messageApi.error(res.error?.message || 'Failed to enable agent');
        }
      } catch (_) {
        messageApi.error('Failed to enable agent');
      }
    }
  }, [id, messageApi, modal, setStatus]);

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

  // Ensure video autoplay when component mounts or mediaUrl changes
  React.useEffect(() => {
    const video = videoRef.current;
    if (!video || !isVideo || !mediaUrl) return;

    // Try to play the video
    const playVideo = async () => {
      try {
        // Don't interrupt if already playing same video
        const currentSrc = video.currentSrc || video.src;
        if (!video.paused && currentSrc === mediaUrl) {
          console.log('[AgentCard] Video already playing same src, skipping autoplay');
          return;
        }
        
        // Only reload if src actually changed
        if (currentSrc !== mediaUrl) {
          console.log('[AgentCard] Loading new video src:', mediaUrl);
          video.src = mediaUrl;
        }
        
        video.muted = true; // Ensure muted for autoplay policy
        video.loop = true; // Ensure loop is enabled
        await video.play();
        console.log('[AgentCard] Video autoplay started successfully');
      } catch (error) {
        console.warn('[AgentCard] Video autoplay failed:', error);
        // Autoplay was prevented, video will play on user interaction
      }
    };

    // Play when video is ready
    if (video.readyState >= 3) {
      // HAVE_FUTURE_DATA or greater
      playVideo();
    } else {
      video.addEventListener('loadeddata', playVideo, { once: true });
    }

    return () => {
      video.removeEventListener('loadeddata', playVideo);
    };
  }, [mediaUrl, isVideo]);

  // Use useEffectOnActive to restart video when component is reactivated from KeepAlive
  useEffectOnActive(
    () => {
      const video = videoRef.current;
      if (!video || !isVideo || !mediaUrl) return;

      console.log('[AgentCard] Reactivating from KeepAlive, ensuring video plays');
      if (video.paused || video.currentSrc !== mediaUrl) {
        if (video.currentSrc !== mediaUrl) {
          video.src = mediaUrl;
        }
        video.muted = true;
        video.loop = true;
        video.play().catch((e) => console.warn('[AgentCard] Reactivation play failed:', e));
      }
    },
    [mediaUrl, isVideo]
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
      // Not playing scene, ensure we're on original src only if src changed
      if (video && originalSrcRef.current) {
        const currentSrc = video.currentSrc || video.src;
        if (currentSrc !== originalSrcRef.current) {
          console.log('[AgentCard] Restoring to original (no scene)');
          video.src = originalSrcRef.current;
          video.loop = true;
          video.currentTime = 0;
          video.play().catch(() => {});
        }
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

            // Refresh in the BACKGROUND — awaiting this inside onOk kept the
            // confirm dialog + full-page mask up for the whole (seconds-long)
            // get_all_org_agents round trip, blocking every other card's menu
            // (2026-09-02 customer report: "3-dot menu stopped working").
            void import('../utils/refreshOrgAgents')
              .then(({ refreshOrgAgents }) => refreshOrgAgents(username))
              .catch((error) => console.error('[AgentCard] Error refreshing org data after delete:', error));
          } else {
            message.error(res.error?.message || (t('common.delete_failed') as string) || 'Delete failed');
          }
        } catch (e: any) {
          message.error(e?.message || t('common.delete_failed') || 'Delete failed');
        }
      }
    });
  };
  
  // Menu items
  const menuItems: MenuProps['items'] = [
    { key: 'edit', label: t('common.edit') || 'Edit', onClick: handleEdit },
    // Enable/Disable toggle
    agentEnabled
      ? { key: 'disable', label: t('pages.agents.disableAgent', 'Disable Agent'), onClick: () => handleSetAgentEnabled(false) }
      : { key: 'enable', label: t('pages.agents.enableAgent', 'Enable Agent'), onClick: () => handleSetAgentEnabled(true) },
    // Start/Stop (only when enabled)
    ...(agentEnabled ? [
      (runtimeStatus === 'stopped')
        ? { key: 'start', icon: <PoweroffOutlined />, label: t('pages.agents.startAgent', 'Start Agent'), onClick: () => handleToggleAgent(true) }
        : (runtimeStatus === 'standby' || runtimeStatus === 'working')
          ? { key: 'stop', icon: <PoweroffOutlined />, label: t('pages.agents.stopAgent', 'Stop Agent'), onClick: () => handleToggleAgent(false), danger: true }
          : null
    ].filter(Boolean) : []),
    { type: 'divider' as const },
    { key: 'delete', label: t('common.delete') || 'Delete', onClick: handleDelete, danger: true },
  ];
  
  return (
    <div 
      className="agent-card" 
      style={{ 
        position: 'relative',
        background: 'linear-gradient(135deg, rgba(59, 130, 246, 0.08) 0%, rgba(147, 51, 234, 0.05) 100%)',
        borderRadius: '16px',
        padding: '20px 20px 12px 20px',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        transition: 'all 0.3s ease',
        cursor: 'pointer',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.transform = 'translateY(-2px)';
        e.currentTarget.style.boxShadow = '0 8px 20px rgba(0, 0, 0, 0.2)';
        e.currentTarget.style.borderColor = 'rgba(59, 130, 246, 0.2)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = 'translateY(0)';
        e.currentTarget.style.boxShadow = 'none';
        e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.08)';
      }}
    >
      {/* 媒体Content */}
      <div style={{ position: 'relative', width: '100%', paddingBottom: '56.25%', marginBottom: '8px' }}>
        {isVideo ? (
          <div
            className="agent-gif-video-wrapper"
            style={{
              position: 'absolute',
              inset: 0,
              borderRadius: '12px',
              background: 'linear-gradient(135deg, rgba(0, 0, 0, 0.6) 0%, rgba(0, 0, 0, 0.4) 100%)',
              border: '2px solid rgba(59, 130, 246, 0.3)',
              boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.1)',
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
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'cover',
                borderRadius: '12px',
                background: 'transparent'
              }}
            />
          </div>
        ) : mediaUrl ? (
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
              objectFit: 'cover',
              borderRadius: '12px',
              background: 'linear-gradient(135deg, rgba(0, 0, 0, 0.6) 0%, rgba(0, 0, 0, 0.4) 100%)',
              border: '2px solid rgba(59, 130, 246, 0.3)',
              boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.1)'
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
        ) : (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              borderRadius: '12px',
              background: 'linear-gradient(135deg, rgba(0, 0, 0, 0.6) 0%, rgba(0, 0, 0, 0.4) 100%)',
              border: '2px solid rgba(59, 130, 246, 0.3)',
              boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.1)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'rgba(255, 255, 255, 0.3)',
              fontSize: '32px'
            }}
          >
            🤖
          </div>
        )}
      </div>
      
      {/* Agent Name + Action Buttons (single row) */}
      <div
        className="agent-info-row"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          width: '100%',
        }}
      >
        {/* Name + status dot (left-aligned, takes remaining space) */}
        <div
          className="agent-name"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            fontSize: '15px',
            fontWeight: 500,
            color: 'var(--text-primary)',
            overflow: 'hidden',
            flex: 1,
            minWidth: 0,
          }}
          title={name ? `${t(name)} (${runtimeStatus})` : ''}
        >
          <Badge
            status={
              runtimeStatus === 'working' ? 'processing' :
              runtimeStatus === 'standby' ? 'success' :
              runtimeStatus === 'stopped' ? 'warning' :
              'default'
            }
          />
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flexShrink: 1, minWidth: 0 }}>
            {name ? t(name) : ''}
          </span>
          {/* Host/machine indicator — pulls from the new discovery directory
              first, falls back to legacy vehicle_id+vehicle store. Renders
              nothing when both sources are silent. */}
          <AgentHostTag agentId={id} vehicleId={(agent as any)?.vehicle_id ?? null} />
          {/* Readiness dots (chrome / site tab / monitor / DOM / detection) from the
              backend [AGENT-STATUS] ledger — hidden until the agent reports. */}
          <ReadinessStrip readiness={runtimeInfo?.readiness} />
        </div>

        {/* Buttons (right-aligned) */}
        <Tooltip title={t('pages.agents.startChat') || 'Start Chat'}>
          <Button
            shape="circle"
            icon={<MessageOutlined />}
            size="small"
            className="agent-chat-btn"
            onClick={(e) => {
              e.stopPropagation();
              onChat?.();
            }}
            style={{
              background: 'rgba(255, 255, 255, 0.05)',
              borderColor: 'rgba(255, 255, 255, 0.1)',
              color: 'rgba(255, 255, 255, 0.7)',
              flexShrink: 0,
            }}
          />
        </Tooltip>

        <AgentTasksButton agentId={id} />

        <Dropdown menu={{ items: menuItems }} trigger={["click"]} placement="bottomRight">
          <Button
            shape="circle"
            icon={<MoreOutlined />}
            size="small"
            onClick={(e) => e.stopPropagation()}
            style={{
              background: 'rgba(255, 255, 255, 0.05)',
              borderColor: 'rgba(255, 255, 255, 0.1)',
              color: 'rgba(255, 255, 255, 0.7)',
              flexShrink: 0,
            }}
          />
        </Dropdown>
      </div>
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
