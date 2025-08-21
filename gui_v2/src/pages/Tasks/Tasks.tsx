import { Button, Spin, Typography, Space } from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
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
  const [isAddingNew, setIsAddingNew] = React.useState(false);

  const listTitle = (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <Text strong>{t('pages.tasks.title')}</Text>
      <Space>
        <Button
          shape="circle"
          icon={<ReloadOutlined />}
          onClick={handleRefresh}
          loading={loading}
          title={t('pages.tasks.refresh')}
        />
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => {
            setIsAddingNew(true);
            // Do not select an empty object; let details render a clean new form
          }}
          title={t('pages.tasks.add')}
        />
      </Space>
    </div>
  );

  const handleTaskSave = () => {
    setIsAddingNew(false);
    handleRefresh(); // Refresh the task list after adding
  };

  return (
    <DetailLayout
      listTitle={listTitle}
      detailsTitle={t('pages.tasks.details')}
      listContent={
        <Spin spinning={loading}>
          <TaskList tasks={tasks} onSelectItem={selectItem} isSelected={isSelected} />
        </Spin>
      }
      detailsContent={
        selectedTask || isAddingNew ? (
          <TaskDetail
            task={isAddingNew ? null : selectedTask}
            isNew={isAddingNew}
            onSave={handleTaskSave}
            onCancel={() => setIsAddingNew(false)}
          />
        ) : null
      }
    />
  );
};

export default Tasks;