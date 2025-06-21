import { Button, Spin, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import React from 'react';

import DetailLayout from '@/components/Layout/DetailLayout';
import { TaskList } from './components/TaskList';
import { TaskDetail } from './components/TaskDetail';
import { useTasks } from './hooks/useTasks';

const { Text } = Typography;

const Tasks: React.FC = () => {
  const { t } = useTranslation();
  const { tasks, selectedTask, selectItem, isSelected, loading, handleRefresh } = useTasks();

  const listTitle = (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <Text strong>{t('pages.tasks.title')}</Text>
      <Button
        shape="circle"
        icon={<ReloadOutlined />}
        onClick={handleRefresh}
        loading={loading}
        title={t('pages.tasks.refresh')}
      />
    </div>
  );

  return (
    <DetailLayout
      listTitle={listTitle}
      detailsTitle={t('pages.tasks.details')}
      listContent={
        <Spin spinning={loading}>
          <TaskList tasks={tasks} onSelectItem={selectItem} isSelected={isSelected} />
        </Spin>
      }
      detailsContent={<TaskDetail task={selectedTask} />}
    />
  );
};

export default Tasks;