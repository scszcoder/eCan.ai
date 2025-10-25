import React, { useState, useMemo } from 'react';
import { Empty, Spin } from 'antd';
import { InboxOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import styled from '@emotion/styled';
import { Task } from '../types';
import { TaskCard } from './TaskCard';
import { TaskFilters, TaskFilterOptions } from './TaskFilters';

const ListContainer = styled.div`
  height: 100%;
  display: flex;
  flex-direction: column;
`;

const TasksScrollArea = styled.div`
  flex: 1;
  padding: 0 8px 8px;
  /* 移除 overflow-y: auto，让 DetailLayout 统一处理滚动 */
`;

const EmptyContainer = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 300px;
`;

interface TaskListProps {
  tasks: Task[];
  loading?: boolean;
  onSelectItem: (task: Task) => void;
  isSelected: (task: Task) => boolean;
}

// 优先级排序权重
const PRIORITY_ORDER: Record<string, number> = {
  ASAP: 5,
  asap: 5,
  URGENT: 4,
  urgent: 4,
  HIGH: 3,
  high: 3,
  MID: 2,
  mid: 2,
  medium: 2,
  LOW: 1,
  low: 1,
  none: 0,
};

export const TaskList: React.FC<TaskListProps> = ({
  tasks,
  loading = false,
  onSelectItem,
  isSelected,
}) => {
  const { t } = useTranslation();
  const [filters, setFilters] = useState<TaskFilterOptions>({
    sortBy: 'priority',
  });

  // 筛选和排序任务
  const filteredAndSortedTasks = useMemo(() => {
    let result = [...tasks];

    // 搜索过滤
    if (filters.search) {
      const searchLower = filters.search.toLowerCase();
      result = result.filter(task =>
        (task.skill?.toLowerCase().includes(searchLower)) ||
        (task.id?.toLowerCase().includes(searchLower))
      );
    }

    // 状态过滤
    if (filters.status) {
      result = result.filter(task => {
        const status = task.state?.top || task.status;
        return status === filters.status;
      });
    }

    // 优先级过滤
    if (filters.priority) {
      result = result.filter(task => task.priority === filters.priority);
    }

    // 触发方式过滤
    if (filters.trigger) {
      result = result.filter(task => task.trigger === filters.trigger);
    }

    // 排序
    result.sort((a, b) => {
      switch (filters.sortBy) {
        case 'priority': {
          const priorityA = PRIORITY_ORDER[a.priority || 'none'] || 0;
          const priorityB = PRIORITY_ORDER[b.priority || 'none'] || 0;
          return priorityB - priorityA; // 高优先级在前
        }
        case 'lastRun': {
          const timeA = a.last_run_datetime ? new Date(a.last_run_datetime).getTime() : 0;
          const timeB = b.last_run_datetime ? new Date(b.last_run_datetime).getTime() : 0;
          return timeB - timeA; // 最近运行的在前
        }
        case 'name': {
          const nameA = a.skill || '';
          const nameB = b.skill || '';
          return nameA.localeCompare(nameB);
        }
        case 'status': {
          const statusA = a.state?.top || a.status || '';
          const statusB = b.state?.top || b.status || '';
          return statusA.localeCompare(statusB);
        }
        default:
          return 0;
      }
    });

    return result;
  }, [tasks, filters]);

  if (loading) {
    return (
      <EmptyContainer>
        <Spin size="large">
          <div style={{ padding: 50 }} />
        </Spin>
      </EmptyContainer>
    );
  }

  return (
    <ListContainer>
      <TaskFilters filters={filters} onChange={setFilters} />

      <TasksScrollArea>
        {filteredAndSortedTasks.length === 0 ? (
          <EmptyContainer>
            <Empty
              image={<InboxOutlined style={{ fontSize: 64, color: '#BFBFBF' }} />}
              description={t('pages.tasks.noTasks', '暂无任务')}
            />
          </EmptyContainer>
        ) : (
          filteredAndSortedTasks.map((task) => (
            <TaskCard
              key={task.id}
              task={task}
              isSelected={isSelected(task)}
              onSelect={onSelectItem}
            />
          ))
        )}
      </TasksScrollArea>
    </ListContainer>
  );
};