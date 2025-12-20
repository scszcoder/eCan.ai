import React, { useState, useMemo, useRef, useEffect } from 'react';
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
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 0;
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
  scrollToTaskId?: string;
}

// PrioritySort权重
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
  scrollToTaskId,
}) => {
  const { t } = useTranslation();
  const [filters, setFilters] = useState<TaskFilterOptions>({
    sortBy: 'priority',
  });
  
  // Used forStorage每个task item的ref
  const taskItemRefs = useRef<Map<string, HTMLDivElement>>(new Map());

  // WhenscrollToTaskId变化时，Scroll到对应的task
  useEffect(() => {
    if (scrollToTaskId && taskItemRefs.current.has(scrollToTaskId)) {
      const element = taskItemRefs.current.get(scrollToTaskId);
      if (element) {
        // 使用setTimeout确保DOM已经Render
        setTimeout(() => {
          element.scrollIntoView({
            behavior: 'smooth',
            block: 'center',
          });
        }, 100);
      }
    }
  }, [scrollToTaskId]);

  // 筛选和Sort任务
  const filteredAndSortedTasks = useMemo(() => {
    let result = [...tasks];

    // SearchFilter
    if (filters.search) {
      const searchLower = filters.search.toLowerCase();
      result = result.filter(task =>
        (task.skill?.toLowerCase().includes(searchLower)) ||
        (task.id?.toLowerCase().includes(searchLower))
      );
    }

    // StatusFilter
    if (filters.status) {
      result = result.filter(task => {
        const status = task.state?.top || task.status;
        return status === filters.status;
      });
    }

    // PriorityFilter
    if (filters.priority) {
      result = result.filter(task => task.priority === filters.priority);
    }

    // Trigger方式Filter
    if (filters.trigger) {
      result = result.filter(task => task.trigger === filters.trigger);
    }

    // Sort
    result.sort((a, b) => {
      switch (filters.sortBy) {
        case 'priority': {
          const priorityA = PRIORITY_ORDER[a.priority || 'none'] || 0;
          const priorityB = PRIORITY_ORDER[b.priority || 'none'] || 0;
          return priorityB - priorityA; // 高Priority在前
        }
        case 'lastRun': {
          const timeA = a.last_run_datetime ? new Date(a.last_run_datetime).getTime() : 0;
          const timeB = b.last_run_datetime ? new Date(b.last_run_datetime).getTime() : 0;
          return timeB - timeA; // 最近Run的在前
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
            <div
              key={task.id}
              ref={(el) => {
                if (el) {
                  taskItemRefs.current.set(task.id, el);
                } else {
                  taskItemRefs.current.delete(task.id);
                }
              }}
            >
              <TaskCard
                task={task}
                isSelected={isSelected(task)}
                onSelect={onSelectItem}
              />
            </div>
          ))
        )}
      </TasksScrollArea>
    </ListContainer>
  );
};