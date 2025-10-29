import { Button, Space, Tooltip } from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import React, { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import styled from '@emotion/styled';

import DetailLayout from '@/components/Layout/DetailLayout';
import { TaskList } from './components/TaskList';
import { TaskDetail } from './components/TaskDetail';
import { useTasks } from './hooks/useTasks';

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
    }

    &:active {
      opacity: 0.8 !important;
    }

    .anticon {
      transition: all 0.3s ease !important;
    }
  }
`;

const Tasks: React.FC = () => {
  const { t } = useTranslation();
  const { tasks, selectedTask, selectItem, isSelected, loading, handleRefresh } = useTasks();
  const [isAddingNew, setIsAddingNew] = React.useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const [scrollToTaskId, setScrollToTaskId] = React.useState<string | undefined>(undefined);
  const [pendingTaskId, setPendingTaskId] = React.useState<string | undefined>(undefined);

  // Handle taskId from URL parameter
  useEffect(() => {
    const taskId = searchParams.get('taskId');
    if (taskId && tasks.length > 0) {
      const task = tasks.find(t => t.id === taskId);
      if (task) {
        // 先Settings要Scroll到的taskId
        setScrollToTaskId(taskId);
        // 然后选中该task
        selectItem(task);
        // 清除URLParameter
        setSearchParams({});
        // 清除scrollToTaskIdStatus（在ScrollCompleted后）
        setTimeout(() => {
          setScrollToTaskId(undefined);
        }, 500);
      }
    }
  }, [searchParams, tasks, selectItem, setSearchParams]);

  // Handle pending task selection after refresh
  useEffect(() => {
    console.log('[Tasks] useEffect 检查 pendingTaskId:', pendingTaskId, 'tasks.length:', tasks.length, 'loading:', loading);
    
    if (pendingTaskId && tasks.length > 0 && !loading) {
      
      const newTask = tasks.find(t => t.id === pendingTaskId);
      
      if (newTask) {
        // 设置要滚动到的task ID
        setScrollToTaskId(pendingTaskId);
        // 选中新创建的task
        selectItem(newTask);
        // 清除pending状态
        setPendingTaskId(undefined);
        // 清除scroll状态
        setTimeout(() => {
          setScrollToTaskId(undefined);
        }, 500);
      } else {
        console.warn('[Tasks] 未找到对应的 task，ID:', pendingTaskId);
      }
    }
  }, [pendingTaskId, tasks, loading, selectItem]);

  const listTitle = (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
      <span style={{ fontSize: '16px', fontWeight: 600, lineHeight: '24px' }}>{t('pages.tasks.title')}</span>
      <Space size={0}>
        <Tooltip title={t('pages.tasks.refresh')}>
          <StyledActionButton
            shape="circle"
            icon={<ReloadOutlined />}
            onClick={handleRefresh}
            loading={loading}
          />
        </Tooltip>
        <Tooltip title={t('pages.tasks.add')}>
          <StyledActionButton
            icon={<PlusOutlined />}
            onClick={() => {
              setIsAddingNew(true);
            }}
          />
        </Tooltip>
      </Space>
    </div>
  );

  const handleTaskSave = async (newTaskId?: string) => {
    setIsAddingNew(false);
    
    // 如果是新创建的task，保存ID等待列表刷新后选中
    if (newTaskId) {
      setPendingTaskId(newTaskId);
    }
    
    await handleRefresh();
  };

  const handleTaskCancel = () => {
    // Cancel时的Process：
    // - If是新建模式，CloseDetails面板
    // - If是Edit模式，不Need额外Process（TaskDetail Internal会Process）
    if (isAddingNew) {
      setIsAddingNew(false);
      selectItem(null as any);
    }
    // Edit模式下，TaskDetail 会自动RestoreData并退出Edit模式，不NeedClose面板
  };

  const handleTaskDelete = () => {
    // Delete后清空选中Status，CloseDetails页
    selectItem(null as any);
    handleRefresh();
  };


  return (
    <DetailLayout
      listTitle={listTitle}
      detailsTitle={t('pages.tasks.details')}
      listContent={
        <TaskList
          tasks={tasks}
          loading={loading}
          onSelectItem={selectItem}
          isSelected={isSelected}
          scrollToTaskId={scrollToTaskId}
        />
      }
      detailsContent={
        selectedTask || isAddingNew ? (
          <TaskDetail
            task={isAddingNew ? null : selectedTask}
            isNew={isAddingNew}
            onSave={handleTaskSave}
            onCancel={handleTaskCancel}
            onDelete={handleTaskDelete}
          />
        ) : null
      }
    />
  );
};

export default Tasks;