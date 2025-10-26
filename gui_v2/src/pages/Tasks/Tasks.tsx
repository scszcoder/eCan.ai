import { Button, Typography, Space } from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import React, { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import styled from '@emotion/styled';

import DetailLayout from '@/components/Layout/DetailLayout';
import { TaskList } from './components/TaskList';
import { TaskDetail } from './components/TaskDetail';
import { useTasks } from './hooks/useTasks';

const { Text } = Typography;

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

  // Handle taskId from URL parameter
  useEffect(() => {
    const taskId = searchParams.get('taskId');
    if (taskId && tasks.length > 0) {
      const task = tasks.find(t => t.id === taskId);
      if (task) {
        // 先设置要滚动到的taskId
        setScrollToTaskId(taskId);
        // 然后选中该task
        selectItem(task);
        // 清除URL参数
        setSearchParams({});
        // 清除scrollToTaskId状态（在滚动完成后）
        setTimeout(() => {
          setScrollToTaskId(undefined);
        }, 500);
      }
    }
  }, [searchParams, tasks, selectItem, setSearchParams]);

  const listTitle = (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <Text strong>{t('pages.tasks.title')}</Text>
      <Space size={0}>
        <StyledActionButton
          shape="circle"
          icon={<ReloadOutlined />}
          onClick={handleRefresh}
          loading={loading}
          title={t('pages.tasks.refresh')}
        />
        <StyledActionButton
          icon={<PlusOutlined />}
          onClick={() => {
            setIsAddingNew(true);
          }}
          title={t('pages.tasks.add')}
        />
      </Space>
    </div>
  );

  const handleTaskSave = () => {
    setIsAddingNew(false);
    handleRefresh();
  };

  const handleTaskDelete = () => {
    // 删除后清空选中状态，关闭详情页
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
            onCancel={() => setIsAddingNew(false)}
            onDelete={handleTaskDelete}
          />
        ) : null
      }
    />
  );
};

export default Tasks;