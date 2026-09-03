import { Button, Space, Tooltip, Modal, message } from 'antd';
import {
  PlusOutlined,
  ReloadOutlined,
  AppstoreOutlined,
  UnorderedListOutlined,
  FullscreenOutlined,
  FullscreenExitOutlined,
  CloseOutlined,
  GroupOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import React, { useEffect, useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import styled from '@emotion/styled';

import DetailLayout from '@/components/Layout/DetailLayout';
import { TaskList } from './components/TaskList';
import { TaskDetail } from './components/TaskDetail';
import { useTasks } from './hooks/useTasks';
import { Task } from './types';
import { get_ipc_api } from '@/services/ipc_api';
import { useUserStore } from '@/stores/userStore';
import { Task as TaskType } from './types';

// View Toggle Button
const ViewToggleButton = styled(Button, {
  shouldForwardProp: (prop) => prop !== '$isActive'
})<{ $isActive?: boolean }>`
  height: 32px !important;
  width: 32px !important;
  min-width: 32px !important;
  padding: 0 !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  border-radius: 6px !important;
  background: ${props => props.$isActive
    ? 'linear-gradient(135deg, rgba(59, 130, 246, 0.9) 0%, rgba(99, 102, 241, 0.9) 100%)'
    : 'transparent'} !important;
  border: ${props => props.$isActive
    ? '1px solid rgba(59, 130, 246, 0.5)'
    : '1px solid transparent'} !important;
  color: ${props => props.$isActive ? 'white' : 'rgba(203, 213, 225, 0.9)'} !important;
  transition: all 0.2s ease !important;

  &:hover {
    background: linear-gradient(135deg, rgba(59, 130, 246, 0.9) 0%, rgba(99, 102, 241, 0.9) 100%) !important;
    color: white !important;
    border-color: rgba(59, 130, 246, 0.5) !important;
  }

  .anticon {
    font-size: 16px;
  }
`;

const ViewToggleContainer = styled.div`
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  margin-left: 8px;
`;

const StyledActionButton = styled(Button)`
  &.ant-btn {
    background: transparent !important;
    border: none !important;
    color: rgba(203, 213, 225, 0.9) !important;
    box-shadow: none !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;

    &:hover {
      background: rgba(255, 255, 255, 0.1) !important;
      color: rgba(248, 250, 252, 0.95) !important;
      transform: translateY(-1px);
    }

    &:active {
      opacity: 0.8 !important;
    }

    .anticon {
      transition: all 0.3s ease !important;
    }
  }
`;

const HeaderTitle = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
`;

const TitleText = styled.span`
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
`;

const TaskCount = styled.span`
  font-size: 12px;
  color: var(--text-secondary);
  background: rgba(255, 255, 255, 0.05);
  padding: 2px 10px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
`;

const TaskDetailModal = styled(Modal)<{ $fullscreen?: boolean }>`
  .ant-modal-content {
    background: var(--bg-primary) !important;
    height: ${props => props.$fullscreen ? '100vh' : '88vh'};
    max-height: ${props => props.$fullscreen ? '100vh' : '88vh'};
    display: flex;
    flex-direction: column;
    padding: 0;
    overflow: hidden;
    border-radius: ${props => props.$fullscreen ? '0' : '16px'};
  }

  .ant-modal-header {
    padding: 14px 18px;
    background: linear-gradient(135deg, rgba(59, 130, 246, 0.12) 0%, rgba(99, 102, 241, 0.08) 100%);
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  }

  .ant-modal-title {
    color: var(--text-primary);
  }

  .ant-modal-body {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    padding: 0;
    overflow: hidden;
  }
`;

const ModalTitleRow = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
`;

const ModalTitleMeta = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
`;

const ModalTitleName = styled.div`
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const ModalActions = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
`;

const Tasks: React.FC = () => {
  const { t } = useTranslation();
  const { tasks, selectedTask, selectItem, unselectItem, isSelected, loading, handleRefresh } = useTasks();
  const [isAddingNew, setIsAddingNew] = React.useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const [scrollToTaskId, setScrollToTaskId] = React.useState<string | undefined>(undefined);
  const [pendingTaskId, setPendingTaskId] = React.useState<string | undefined>(undefined);
  const [viewMode, setViewMode] = React.useState<'list' | 'grid' | 'group'>('grid');
  const [isGridDetailOpen, setIsGridDetailOpen] = React.useState(false);
  const [isGridDetailFullscreen, setIsGridDetailFullscreen] = React.useState(false);
  const username = useUserStore((s) => s.username) || '';
  
  // Calculate quick stats for filter tags
  const quickStats = useMemo(() => {
    return {
      all: tasks.length,
      running: tasks.filter(t => ['running', 'working'].includes((t.state?.top || t.status || '').toLowerCase())).length,
      ready: tasks.filter(t => (t.state?.top || t.status || '').toLowerCase() === 'ready').length,
      pending: tasks.filter(t => ['pending', 'submitted'].includes((t.state?.top || t.status || '').toLowerCase())).length,
      failed: tasks.filter(t => ['failed', 'canceled'].includes((t.state?.top || t.status || '').toLowerCase())).length,
    };
  }, [tasks]);
  const statistics = React.useMemo(() => {
    const stats = {
      total: tasks.length,
      running: 0,
      pending: 0,
      completed: 0,
      failed: 0,
    };
    tasks.forEach(task => {
      const status = (task.state?.top || task.status || 'unknown').toLowerCase();
      if (status === 'running' || status === 'working') stats.running++;
      else if (status === 'pending' || status === 'submitted') stats.pending++;
      else if (status === 'completed') stats.completed++;
      else if (status === 'failed' || status === 'canceled') stats.failed++;
    });
    return stats;
  }, [tasks]);

  const selectedTaskIndex = React.useMemo(() => {
    if (!selectedTask || isAddingNew) return -1;
    return tasks.findIndex((task) => task.id === (selectedTask as TaskType)?.id);
  }, [tasks, selectedTask, isAddingNew]);

  const hasPrevTask = selectedTaskIndex > 0;
  const hasNextTask = selectedTaskIndex >= 0 && selectedTaskIndex < tasks.length - 1;

  // Handle view mode change
  const handleViewModeChange = React.useCallback((mode: 'list' | 'grid' | 'group') => {
    setViewMode(mode);
    if (mode !== 'grid') {
      setIsGridDetailOpen(false);
      setIsGridDetailFullscreen(false);
    }
  }, []);


  // Handle taskId from URL parameter
  useEffect(() => {
    const taskId = searchParams.get('taskId');
    if (taskId && tasks.length > 0) {
      const task = tasks.find(t => t.id === taskId);
      if (task) {
          setScrollToTaskId(taskId);
          selectItem(task);
          if (viewMode === 'grid') {
            setIsGridDetailOpen(true);
          }
          setSearchParams({});
        setTimeout(() => {
          setScrollToTaskId(undefined);
        }, 500);
      }
    }
  }, [searchParams, tasks, selectItem, setSearchParams, viewMode]);

  // Handle pending task selection after refresh
  useEffect(() => {
    if (pendingTaskId && tasks.length > 0 && !loading) {
      const newTask = tasks.find(t => t.id === pendingTaskId);
      if (newTask) {
        setScrollToTaskId(pendingTaskId);
        selectItem(newTask);
        if (viewMode === 'grid') {
          setIsGridDetailOpen(true);
        }
        setPendingTaskId(undefined);
        setTimeout(() => {
          setScrollToTaskId(undefined);
        }, 500);
      }
    }
  }, [pendingTaskId, tasks, loading, selectItem, viewMode]);

  // Handle batch actions
  const handleBatchAction = useCallback(async (action: string, selectedTasks: Task[]) => {
    if (selectedTasks.length === 0) return;

    const api = get_ipc_api();

    switch (action) {
      case 'run':
        Modal.confirm({
          title: t('pages.tasks.batchActions.runConfirm', '确认运行'),
          content: t('pages.tasks.batchActions.runConfirmContent', {
            count: selectedTasks.length,
            defaultValue: `确定要运行选中的 ${selectedTasks.length} 个任务吗？`,
          }),
          okText: t('common.confirm', '确认'),
          cancelText: t('common.cancel', '取消'),
          async onOk() {
            for (const task of selectedTasks) {
              try {
                await api.runAgentTask(username, {
                  task_id: task.id,
                  task_type: task.task_type || 'local',
                  cloud_based: (task.task_type || 'local') !== 'local',
                });
              } catch (e) {
                console.error(`[Tasks] Failed to run task ${task.id}:`, e);
              }
            }
            message.success(t('pages.tasks.batchActions.runSuccess', { count: selectedTasks.length, defaultValue: `${selectedTasks.length} 个任务已启动` }));
          },
        });
        break;

      case 'duplicate':
        Modal.confirm({
          title: t('pages.tasks.batchActions.duplicateConfirm', '确认复制'),
          content: t('pages.tasks.batchActions.duplicateConfirmContent', {
            count: selectedTasks.length,
            defaultValue: `确定要复制选中的 ${selectedTasks.length} 个任务吗？`,
          }),
          okText: t('common.confirm', '确认'),
          cancelText: t('common.cancel', '取消'),
          async onOk() {
            for (const task of selectedTasks) {
              try {
                const duplicatedTask = {
                  ...task,
                  id: `task_${Date.now()}_${Math.random().toString(36).substring(2, 8)}`,
                  name: `${task.name || 'Task'} (Copy)`,
                };
                delete duplicatedTask.state;
                delete duplicatedTask.status;
                await api.newAgentTask(username, duplicatedTask);
              } catch (e) {
                console.error(`[Tasks] Failed to duplicate task ${task.id}:`, e);
              }
            }
            message.success(t('pages.tasks.batchActions.duplicateSuccess', { count: selectedTasks.length, defaultValue: `${selectedTasks.length} 个任务已复制` }));
            await handleRefresh();
          },
        });
        break;

      case 'delete':
        Modal.confirm({
          title: t('pages.tasks.batchActions.deleteConfirm', '确认删除'),
          content: t('pages.tasks.batchActions.deleteConfirmContent', {
            count: selectedTasks.length,
            defaultValue: `确定要删除选中的 ${selectedTasks.length} 个任务吗？此操作无法撤销。`,
          }),
          okText: t('common.delete', '删除'),
          cancelText: t('common.cancel', '取消'),
          okButtonProps: { danger: true },
          async onOk() {
            for (const task of selectedTasks) {
              try {
                await api.deleteAgentTask(username, task.id);
              } catch (e) {
                console.error(`[Tasks] Failed to delete task ${task.id}:`, e);
              }
            }
            message.success(t('pages.tasks.batchActions.deleteSuccess', { count: selectedTasks.length, defaultValue: `${selectedTasks.length} 个任务已删除` }));
            // Close the grid detail modal BEFORE clearing the selection:
            // it renders <TaskDetail task={selectedTask} isNew={false}> gated
            // only on isGridDetailOpen, so a cleared selection with the modal
            // still open crashed TaskDetail (task=null) → route-level
            // 渲染失败 boundary until a manual page refresh.
            setIsGridDetailOpen(false);
            setIsAddingNew(false);
            selectItem(null as any);
            await handleRefresh();
          },
        });
        break;

      default:
        break;
    }
  }, [username, t, handleRefresh, selectItem]);

  // listTitle: compact header with title, stats, view toggle, and actions
  const listTitle = (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
      <HeaderTitle>
        <TitleText>{t('pages.tasks.title', '任务管理')}</TitleText>
        <TaskCount>
          {statistics.total} {t('pages.tasks.count', '个任务')}
          {statistics.running > 0 && <span style={{ color: '#1890FF', marginLeft: 8 }}>{statistics.running} 运行中</span>}
        </TaskCount>
      </HeaderTitle>
      <Space size={8}>
        {/* View Toggle */}
        <ViewToggleContainer>
          <Tooltip title={t('pages.tasks.view.list', '列表视图')}>
            <ViewToggleButton
              $isActive={viewMode === 'list'}
              onClick={() => handleViewModeChange('list')}
              icon={<UnorderedListOutlined />}
            />
          </Tooltip>
          <Tooltip title={t('pages.tasks.view.grid', '网格视图')}>
            <ViewToggleButton
              $isActive={viewMode === 'grid'}
              onClick={() => handleViewModeChange('grid')}
              icon={<AppstoreOutlined />}
            />
          </Tooltip>
          <Tooltip title={t('pages.tasks.view.group', '分组视图')}>
            <ViewToggleButton
              $isActive={viewMode === 'group'}
              onClick={() => handleViewModeChange('group')}
              icon={<GroupOutlined />}
            />
          </Tooltip>
        </ViewToggleContainer>

        <Tooltip title={t('pages.tasks.refresh', '刷新')}>
          <StyledActionButton
            shape="circle"
            icon={<ReloadOutlined spin={loading} />}
            onClick={handleRefresh}
            loading={loading}
          />
        </Tooltip>
        <Tooltip title={t('pages.tasks.add', '新建任务')}>
          <StyledActionButton
            shape="circle"
            icon={<PlusOutlined />}
            onClick={() => {
              setIsAddingNew(true);
              if (viewMode === 'grid') {
                setIsGridDetailOpen(true);
              }
            }}
          />
        </Tooltip>
      </Space>
    </div>
  );

  const handleTaskSave = async (newTaskId?: string) => {
    setIsAddingNew(false);
    if (newTaskId) {
      setPendingTaskId(newTaskId);
    }
    await handleRefresh();
  };

  const handleTaskCancel = () => {
    if (isAddingNew) {
      setIsAddingNew(false);
      setIsGridDetailOpen(false);
      unselectItem();
    }
  };

  const handleTaskDelete = async () => {
    unselectItem();
    await handleRefresh();
  };

  const handleSelectPrevTask = useCallback(() => {
    if (!hasPrevTask) return;
    const prevTask = tasks[selectedTaskIndex - 1];
    if (prevTask) selectItem(prevTask);
  }, [hasPrevTask, selectedTaskIndex, tasks, selectItem]);

  const handleSelectNextTask = useCallback(() => {
    if (!hasNextTask) return;
    const nextTask = tasks[selectedTaskIndex + 1];
    if (nextTask) selectItem(nextTask);
  }, [hasNextTask, selectedTaskIndex, tasks, selectItem]);

  // Handle task reordering (for drag and drop)
  const handleTasksReorder = useCallback((reorderedTasks: Task[]) => {
    // This would need to be connected to the backend to persist the order
    // For now, just log it - in a real implementation, you'd save the new order
    console.log('[Tasks] Tasks reordered:', reorderedTasks.map(t => t.id));
  }, []);

  useEffect(() => {
    if (!isGridDetailOpen) return;

      const handleCloseGridDetail = () => {
      setIsAddingNew(false);
      setIsGridDetailOpen(false);
      unselectItem();
      setIsGridDetailFullscreen(false);
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const tagName = target?.tagName?.toLowerCase();
      const isEditable = !!target?.isContentEditable || tagName === 'input' || tagName === 'textarea' || tagName === 'select';

      if (event.key === 'Escape') {
        event.preventDefault();
        handleCloseGridDetail();
        return;
      }

      if (isEditable) return;

      if (event.key === 'ArrowLeft' && hasPrevTask && !isAddingNew) {
        event.preventDefault();
        const prevTask = tasks[selectedTaskIndex - 1];
        if (prevTask) selectItem(prevTask);
      }

      if (event.key === 'ArrowRight' && hasNextTask && !isAddingNew) {
        event.preventDefault();
        const nextTask = tasks[selectedTaskIndex + 1];
        if (nextTask) selectItem(nextTask);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [hasNextTask, hasPrevTask, isAddingNew, isGridDetailOpen, selectedTaskIndex, selectItem, tasks, unselectItem]);

  return (
    <>
      <DetailLayout
      listTitle={listTitle}
      detailsTitle={t('pages.tasks.details', '详情')}
      listContent={
        <TaskList
          tasks={tasks}
          loading={loading}
          onSelectItem={(task) => {
            selectItem(task);
            if (viewMode === 'grid') {
              setIsGridDetailOpen(true);
            }
          }}
          isSelected={isSelected}
          scrollToTaskId={scrollToTaskId}
          onBatchAction={handleBatchAction}
          onRefresh={handleRefresh}
          viewMode={viewMode}
          onTasksReorder={handleTasksReorder}
          quickStats={quickStats}
        />
      }
      detailsContent={
        viewMode === 'list' && (selectedTask || isAddingNew) ? (
          <TaskDetail
            task={isAddingNew ? null : selectedTask}
            isNew={isAddingNew}
            onSave={handleTaskSave}
            onCancel={handleTaskCancel}
            onDelete={handleTaskDelete}
            onPrev={handleSelectPrevTask}
            onNext={handleSelectNextTask}
            hasPrev={hasPrevTask}
            hasNext={hasNextTask}
          />
        ) : undefined
      }
      defaultListWidth={viewMode === 'grid' ? 560 : 400}
      minListWidth={viewMode === 'grid' ? 480 : 340}
      maxListWidth={viewMode === 'grid' ? 700 : 600}
      fillListAvailableWidth={viewMode === 'grid'}
      fillDetailsAvailableWidth={viewMode === 'list'}
    />

      <TaskDetailModal
        open={isGridDetailOpen}
        onCancel={() => {
          setIsAddingNew(false);
          setIsGridDetailOpen(false);
          unselectItem();
          setIsGridDetailFullscreen(false);
        }}
        footer={null}
        width={isGridDetailFullscreen ? '100vw' : 'min(1100px, 92vw)'}
        style={isGridDetailFullscreen ? { top: 0, paddingBottom: 0 } : undefined}
        centered={!isGridDetailFullscreen}
        destroyOnHidden={false}
        closable={false}
        $fullscreen={isGridDetailFullscreen}
        title={
          <ModalTitleRow>
            <ModalTitleMeta>
              <ModalTitleName>
                {isAddingNew
                  ? t('pages.tasks.add', '新建任务')
                  : ((selectedTask as TaskType | null)?.name || t('pages.tasks.details', '详情'))}
              </ModalTitleName>
            </ModalTitleMeta>
            <ModalActions>
              <Tooltip title={isGridDetailFullscreen ? t('common.exitFullscreen', '退出全屏') : t('common.fullscreen', '全屏')}>
                <StyledActionButton
                  shape="circle"
                  icon={isGridDetailFullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
                  onClick={() => setIsGridDetailFullscreen((prev) => !prev)}
                />
              </Tooltip>
              <Tooltip title={t('common.close', '关闭')}>
                <StyledActionButton
                  shape="circle"
                  icon={<CloseOutlined />}
                  onClick={() => {
                    setIsAddingNew(false);
                    setIsGridDetailOpen(false);
                    unselectItem();
                    setIsGridDetailFullscreen(false);
                  }}
                />
              </Tooltip>
            </ModalActions>
          </ModalTitleRow>
        }
      >
        {isGridDetailOpen && (selectedTask || isAddingNew) ? (
          <>
            <TaskDetail
              task={isAddingNew ? null : selectedTask}
              isNew={isAddingNew}
              onSave={handleTaskSave}
              onCancel={handleTaskCancel}
              onDelete={handleTaskDelete}
              onPrev={handleSelectPrevTask}
              onNext={handleSelectNextTask}
              hasPrev={hasPrevTask}
              hasNext={hasNextTask}
            />
          </>
        ) : null}
      </TaskDetailModal>
    </>
  );
};

export default Tasks;
