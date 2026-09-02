import React, { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import { Spin, Checkbox, Button, Modal } from 'antd';
import {
  InboxOutlined,
  PlayCircleOutlined,
  DeleteOutlined,
  BorderOutlined,
  CheckSquareOutlined,
  LoadingOutlined,
  FullscreenExitOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import styled from '@emotion/styled';
import { keyframes } from '@emotion/react';
import { Task } from '../types';
import { TaskCard } from './TaskCard';
import { TaskFilters, TaskFilterOptions } from './TaskFilters';

const fadeInAnimation = keyframes`
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
`;

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
  
  &::-webkit-scrollbar {
    width: 6px;
  }
  
  &::-webkit-scrollbar-track {
    background: rgba(255, 255, 255, 0.02);
    border-radius: 3px;
  }
  
  &::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.1);
    border-radius: 3px;
    
    &:hover {
      background: rgba(255, 255, 255, 0.15);
    }
  }
`;

const EmptyContainer = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 300px;
  animation: ${fadeInAnimation} 0.3s ease-out;
`;

const EmptyIcon = styled.div`
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: rgba(59, 130, 246, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 16px;
  
  .anticon {
    font-size: 36px;
    color: rgba(59, 130, 246, 0.5);
  }
`;

const EmptyText = styled.div`
  color: var(--text-secondary);
  font-size: 14px;
  margin-bottom: 16px;
`;

const EmptyAction = styled(Button)`
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.9) 0%, rgba(99, 102, 241, 0.9) 100%);
  border: none;
  border-radius: 8px;
  height: 36px;
  
  &:hover {
    background: linear-gradient(135deg, rgba(59, 130, 246, 1) 0%, rgba(99, 102, 241, 1) 100%);
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4);
  }
`;

// View Mode types
export type ViewMode = 'list' | 'grid' | 'group';

// Fullscreen Modal Container
const FullscreenModal = styled(Modal)`
  .ant-modal-content {
    background: var(--bg-primary) !important;
    height: 90vh;
    max-height: 90vh;
    display: flex;
    flex-direction: column;
  }

  .ant-modal-header {
    flex-shrink: 0;
    background: transparent;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    padding: 16px 24px;
  }

  .ant-modal-body {
    flex: 1;
    min-height: 0;
    overflow: hidden;
    padding: 0;
  }

  .ant-modal-footer {
    flex-shrink: 0;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
  }
`;

// Grid Container for Grid View
const TasksGridContainer = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
  padding: 4px;
  align-items: start;

  @media (min-width: 1600px) {
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  }

  @media (max-width: 1200px) {
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  }

  @media (max-width: 768px) {
    grid-template-columns: 1fr;
  }
`;

// List Container for List View
const TasksListContainer = styled.div`
  display: flex;
  flex-direction: column;
  gap: 8px;
`;

// Batch Actions Bar
const BatchActionsBar = styled.div<{ $visible: boolean }>`
  display: ${props => props.$visible ? 'flex' : 'none'};
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.15) 0%, rgba(99, 102, 241, 0.1) 100%);
  border-bottom: 1px solid rgba(59, 130, 246, 0.2);
  flex-shrink: 0;
  animation: ${fadeInAnimation} 0.2s ease-out;
`;

const SelectedCount = styled.span`
  font-size: 13px;
  color: rgba(255, 255, 255, 0.9);
  font-weight: 500;
`;

const BatchButton = styled(Button)`
  height: 32px;
  border-radius: 6px;
  font-size: 13px;
  
  &.ant-btn-primary {
    background: linear-gradient(135deg, #1890FF 0%, #096dd9 100%);
    border: none;
  }
  
  &.ant-btn-default {
    background: rgba(255, 255, 255, 0.1);
    border: 1px solid rgba(255, 255, 255, 0.15);
    color: var(--text-primary);
  }
  
  &.ant-btn-dangerous {
    background: linear-gradient(135deg, #ff4d4f 0%, #cf1322 100%);
    border: none;
  }
`;

const SelectAllCheckbox = styled(Checkbox)`
  padding: 4px 8px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 6px;
  
  .ant-checkbox-inner {
    border-radius: 4px;
  }
`;

// Grouping View Container
const GroupedTasksContainer = styled.div`
  display: flex;
  flex-direction: column;
  gap: 16px;
`;

const TaskGroup = styled.div`
  animation: ${fadeInAnimation} 0.3s ease-out;
`;

const GroupHeader = styled.div<{ $color?: string }>`
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  margin-bottom: 8px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 8px;
  border-left: 3px solid ${props => props.$color || 'var(--primary-color)'};
`;

const GroupTitle = styled.div`
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
`;

const GroupCount = styled.span`
  font-size: 11px;
  color: var(--text-muted);
  background: rgba(255, 255, 255, 0.08);
  padding: 2px 8px;
  border-radius: 10px;
`;

// Dragging styles
const DraggingItem = styled.div<{ $isDragging?: boolean }>`
  opacity: ${props => props.$isDragging ? 0.5 : 1};
  transform: ${props => props.$isDragging ? 'scale(1.02)' : 'scale(1)'};
  transition: all 0.2s ease;
`;

const DropIndicator = styled.div`
  height: 4px;
  background: linear-gradient(90deg, rgba(59, 130, 246, 0.8), rgba(99, 102, 241, 0.8));
  border-radius: 2px;
  margin: 4px 0;
  animation: ${fadeInAnimation} 0.15s ease-out;
`;

// Priority Sort weights
const PRIORITY_ORDER: Record<string, number> = {
  ASAP: 5,
  URGENT: 4,
  HIGH: 3,
  MID: 2,
  LOW: 1,
  none: 0,
};

// Status sort order
const STATUS_ORDER: Record<string, number> = {
  running: 5,
  working: 5,
  pending: 4,
  submitted: 3,
  input_required: 2,
  ready: 1,
  completed: 0,
  failed: -1,
  canceled: -2,
  unknown: -3,
};

interface TaskListProps {
  tasks: Task[];
  loading?: boolean;
  onSelectItem: (task: Task) => void;
  isSelected: (task: Task) => boolean;
  scrollToTaskId?: string;
  onBatchAction?: (action: string, tasks: Task[]) => void;
  onRefresh?: () => void;
  viewMode?: ViewMode;
  isFullscreen?: boolean;
  onFullscreenChange?: (val: boolean) => void;
  onTasksReorder?: (tasks: Task[]) => void;
  quickStats?: {
    all: number;
    running: number;
    ready: number;
    pending: number;
    failed: number;
  };
}

export const TaskList: React.FC<TaskListProps> = ({
  tasks,
  loading = false,
  onSelectItem,
  isSelected,
  scrollToTaskId,
  onBatchAction,
  viewMode: externalViewMode,
  isFullscreen: externalFullscreen,
  onFullscreenChange,
  onTasksReorder,
  quickStats,
}) => {
  const { t } = useTranslation();
  const viewMode = externalViewMode || 'list';

  const [internalFullscreen, setInternalFullscreen] = useState(false);
  const isFullscreen = externalFullscreen ?? internalFullscreen;
  const setIsFullscreen = useCallback((val: boolean) => {
    setInternalFullscreen(val);
    onFullscreenChange?.(val);
  }, [onFullscreenChange]);

  const [fullscreenTask, setFullscreenTask] = useState<Task | null>(null);
  const [filters, setFilters] = useState<TaskFilterOptions>({
    sortBy: 'priority',
    sortOrder: 'desc',
  });
  const [selectedTaskIds, setSelectedTaskIds] = useState<Set<string>>(new Set());
  const [isSelectMode, setIsSelectMode] = useState(false);
  const [draggedTaskId, setDraggedTaskId] = useState<string | null>(null);
  const [dropTargetIndex, setDropTargetIndex] = useState<number | null>(null);
  
  // Store refs for each task item
  const taskItemRefs = useRef<Map<string, HTMLDivElement>>(new Map());

  // Calculate statistics
  const statistics = useMemo(() => {
    const stats = {
      total: tasks.length,
      running: 0,
      ready: 0,
      pending: 0,
      completed: 0,
      failed: 0,
      byPriority: { ASAP: 0, URGENT: 0, HIGH: 0, MID: 0, LOW: 0, none: 0 },
    };

    tasks.forEach(task => {
      const status = (task.state?.top || task.status || 'unknown').toLowerCase();
      const priority = (task.priority || 'none').toUpperCase();

      if (status === 'running' || status === 'working') {
        stats.running++;
      } else if (status === 'ready') {
        stats.ready++;
      } else if (status === 'pending' || status === 'submitted') {
        stats.pending++;
      } else if (status === 'completed') {
        stats.completed++;
      } else if (status === 'failed' || status === 'canceled') {
        stats.failed++;
      }

      if (priority in stats.byPriority) {
        stats.byPriority[priority as keyof typeof stats.byPriority]++;
      }
    });

    return stats;
  }, [tasks]);

  // Use quickStats from parent if available, otherwise calculate from statistics
  const displayStats = quickStats || {
    all: statistics.total,
    running: statistics.running,
    ready: statistics.ready,
    pending: statistics.pending,
    failed: statistics.failed,
  };

  // Filter and sort tasks
  const filteredAndSortedTasks = useMemo(() => {
    let result = [...tasks];

    // Search Filter
    if (filters.search) {
      const searchLower = filters.search.toLowerCase();
      result = result.filter(task =>
        (task.name?.toLowerCase().includes(searchLower)) ||
        (task.id?.toLowerCase().includes(searchLower)) ||
        (task.description?.toLowerCase().includes(searchLower))
      );
    }

    // Status Filter
    if (filters.status) {
      result = result.filter(task => {
        const status = (task.state?.top || task.status || '').toLowerCase();
        return status === filters.status?.toLowerCase();
      });
    }

    // Priority Filter
    if (filters.priority) {
      result = result.filter(task => {
        const priority = (task.priority || 'none').toUpperCase();
        return priority === filters.priority?.toUpperCase();
      });
    }

    // Task Type Filter
    if (filters.taskType) {
      result = result.filter(task => {
        const taskType = task.task_type || task.metadata?.task_type || 'local';
        return taskType === filters.taskType;
      });
    }

    // Sort
    result.sort((a, b) => {
      let comparison = 0;
      
      switch (filters.sortBy) {
        case 'priority': {
          const priorityA = PRIORITY_ORDER[a.priority?.toUpperCase() || 'NONE'] || 0;
          const priorityB = PRIORITY_ORDER[b.priority?.toUpperCase() || 'NONE'] || 0;
          comparison = priorityB - priorityA;
          break;
        }
        case 'lastRun': {
          const timeA = a.last_run_datetime ? new Date(a.last_run_datetime).getTime() : 0;
          const timeB = b.last_run_datetime ? new Date(b.last_run_datetime).getTime() : 0;
          comparison = timeB - timeA;
          break;
        }
        case 'name': {
          const nameA = a.name || '';
          const nameB = b.name || '';
          comparison = nameA.localeCompare(nameB);
          break;
        }
        case 'status': {
          const statusA = STATUS_ORDER[(a.state?.top || a.status || '').toLowerCase()] || 0;
          const statusB = STATUS_ORDER[(b.state?.top || b.status || '').toLowerCase()] || 0;
          comparison = statusB - statusA;
          break;
        }
        default:
          comparison = 0;
      }

      // Apply sort order
      return filters.sortOrder === 'asc' ? -comparison : comparison;
    });

    return result;
  }, [tasks, filters]);

  // Grouped tasks by status for group view
  const groupedTasks = useMemo(() => {
    if (viewMode !== 'group') return null;

    const groups: Record<string, { tasks: Task[]; color: string; label: string }> = {
      running: { tasks: [], color: '#1890FF', label: t('pages.tasks.status.running', '运行中') },
      pending: { tasks: [], color: '#722ed1', label: t('pages.tasks.status.pending', '待处理') },
      ready: { tasks: [], color: '#52C41A', label: t('pages.tasks.status.ready', '就绪') },
      completed: { tasks: [], color: '#8c8c8c', label: t('pages.tasks.status.completed', '已完成') },
      failed: { tasks: [], color: '#FF4D4F', label: t('pages.tasks.status.failed', '失败') },
    };

    filteredAndSortedTasks.forEach(task => {
      const status = (task.state?.top || task.status || 'unknown').toLowerCase();
      if (status === 'running' || status === 'working') {
        groups.running.tasks.push(task);
      } else if (status === 'pending' || status === 'submitted') {
        groups.pending.tasks.push(task);
      } else if (status === 'ready') {
        groups.ready.tasks.push(task);
      } else if (status === 'completed') {
        groups.completed.tasks.push(task);
      } else if (status === 'failed' || status === 'canceled') {
        groups.failed.tasks.push(task);
      }
    });

    // Only return non-empty groups
    return Object.entries(groups)
      .filter(([_, group]) => group.tasks.length > 0)
      .map(([key, group]) => ({ key, ...group }));
  }, [filteredAndSortedTasks, viewMode, t]);

  // Scroll to task when scrollToTaskId changes
  useEffect(() => {
    if (scrollToTaskId && taskItemRefs.current.has(scrollToTaskId)) {
      const element = taskItemRefs.current.get(scrollToTaskId);
      if (element) {
        setTimeout(() => {
          element.scrollIntoView({
            behavior: 'smooth',
            block: 'center',
          });
        }, 100);
      }
    }
  }, [scrollToTaskId]);

  // Drag and drop handlers for reordering
  const handleDragStart = useCallback((e: React.DragEvent, taskId: string) => {
    setDraggedTaskId(taskId);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', taskId);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent, index: number) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    if (dropTargetIndex !== index) {
      setDropTargetIndex(index);
    }
  }, [dropTargetIndex]);

  const handleDragLeave = useCallback(() => {
    setDropTargetIndex(null);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent, dropIndex: number) => {
    e.preventDefault();
    if (!draggedTaskId || !onTasksReorder) {
      setDraggedTaskId(null);
      setDropTargetIndex(null);
      return;
    }

    const dragIndex = filteredAndSortedTasks.findIndex(t => t.id === draggedTaskId);
    if (dragIndex === -1 || dragIndex === dropIndex) {
      setDraggedTaskId(null);
      setDropTargetIndex(null);
      return;
    }

    // Reorder tasks
    const newTasks = [...filteredAndSortedTasks];
    const [removed] = newTasks.splice(dragIndex, 1);
    newTasks.splice(dropIndex, 0, removed);
    onTasksReorder(newTasks);

    setDraggedTaskId(null);
    setDropTargetIndex(null);
  }, [draggedTaskId, dropTargetIndex, filteredAndSortedTasks, onTasksReorder]);

  const handleDragEnd = useCallback(() => {
    setDraggedTaskId(null);
    setDropTargetIndex(null);
  }, []);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsSelectMode(false);
        setSelectedTaskIds(new Set());
      }
      
      if ((e.ctrlKey || e.metaKey) && e.key === 'a' && !isSelectMode) {
        e.preventDefault();
        setIsSelectMode(true);
        setSelectedTaskIds(new Set(filteredAndSortedTasks.map(t => t.id)));
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [filteredAndSortedTasks, isSelectMode]);

  // Handle task card action
  // NOTE: For 'edit' and 'view' we must call the real selectItem directly.
  const handleTaskAction = useCallback((action: string, task: Task) => {
    switch (action) {
      case 'view':
        onSelectItem(task);
        break;
      case 'run':
        onBatchAction?.('run', [task]);
        break;
      case 'duplicate':
        onBatchAction?.('duplicate', [task]);
        break;
      case 'edit':
        onSelectItem(task);
        break;
      case 'delete':
        onBatchAction?.('delete', [task]);
        break;
      default:
        break;
    }
  }, [onSelectItem, onBatchAction]);

  // Handle expanding from grid card
  const handleExpandTask = useCallback((task: Task) => {
    setFullscreenTask(task);
    setIsFullscreen(true);
  }, []);

  // Handle fullscreen modal close
  const handleCloseFullscreen = useCallback(() => {
    setIsFullscreen(false);
    setFullscreenTask(null);
  }, []);

  const handleSelectAll = () => {
    if (selectedTaskIds.size === filteredAndSortedTasks.length) {
      setSelectedTaskIds(new Set());
    } else {
      setSelectedTaskIds(new Set(filteredAndSortedTasks.map(t => t.id)));
    }
  };

  // In select mode a card click toggles membership instead of opening the
  // task; selection highlight reuses the card's isSelected styling.
  const handleCardSelect = useCallback((task: Task) => {
    if (isSelectMode) {
      setSelectedTaskIds(prev => {
        const next = new Set(prev);
        if (next.has(task.id)) next.delete(task.id);
        else next.add(task.id);
        return next;
      });
      return;
    }
    onSelectItem(task);
  }, [isSelectMode, onSelectItem]);

  const cardIsSelected = useCallback((task: Task) =>
    isSelectMode ? selectedTaskIds.has(task.id) : isSelected(task),
    [isSelectMode, selectedTaskIds, isSelected]);

  const runBatch = (action: string) => {
    const chosen = filteredAndSortedTasks.filter(t => selectedTaskIds.has(t.id));
    if (!chosen.length) return;
    onBatchAction?.(action, chosen);
    setIsSelectMode(false);
    setSelectedTaskIds(new Set());
  };

  if (loading) {
    return (
      <EmptyContainer>
        <Spin size="large" indicator={<LoadingOutlined style={{ fontSize: 36, color: '#1890FF' }} spin />} />
        <div style={{ marginTop: 16, color: 'var(--text-muted)' }}>
          {t('common.loading', '加载中...')}
        </div>
      </EmptyContainer>
    );
  }

  return (
    <ListContainer>
      {/* Filters */}
      <TaskFilters
        filters={filters}
        onChange={setFilters}
        totalCount={tasks.length}
        filteredCount={filteredAndSortedTasks.length}
        quickStats={displayStats}
      />

      {/* Batch-select entry: the old Ctrl+A-only path was undiscoverable —
          customers deleted tasks one by one (2026-09-02 report). */}
      {!isSelectMode && selectedTaskIds.size === 0 && filteredAndSortedTasks.length > 0 && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', padding: '2px 0' }}>
          <Button
            size="small"
            icon={<CheckSquareOutlined />}
            onClick={() => setIsSelectMode(true)}
          >
            {t('pages.tasks.batchSelect', '批量选择')}
          </Button>
        </div>
      )}

      {/* Batch Actions Bar */}
      <BatchActionsBar $visible={isSelectMode || selectedTaskIds.size > 0}>
        <SelectAllCheckbox
          checked={selectedTaskIds.size === filteredAndSortedTasks.length && filteredAndSortedTasks.length > 0}
          indeterminate={selectedTaskIds.size > 0 && selectedTaskIds.size < filteredAndSortedTasks.length}
          onChange={handleSelectAll}
        >
          <span style={{ fontSize: 13, color: 'var(--text-primary)' }}>
            {t('pages.tasks.selectAll', '全选')}
          </span>
        </SelectAllCheckbox>

        <SelectedCount>
          {t('pages.tasks.selectedCount', { count: selectedTaskIds.size })}
        </SelectedCount>

        <div style={{ flex: 1 }} />

        <BatchButton
          icon={<PlayCircleOutlined />}
          onClick={() => runBatch('run')}
          disabled={selectedTaskIds.size === 0}
        >
          {t('pages.tasks.actions.run', '运行')}
        </BatchButton>

        <BatchButton
          danger
          icon={<DeleteOutlined />}
          onClick={() => runBatch('delete')}
          disabled={selectedTaskIds.size === 0}
        >
          {t('pages.tasks.actions.delete', '删除')}
        </BatchButton>

        <Button
          type="text"
          size="small"
          icon={<BorderOutlined />}
          onClick={() => {
            setIsSelectMode(false);
            setSelectedTaskIds(new Set());
          }}
          style={{ color: 'var(--text-secondary)' }}
        >
          {t('pages.tasks.cancelSelection', '取消')}
        </Button>
      </BatchActionsBar>

      {/* Task List */}
      <TasksScrollArea>
        {filteredAndSortedTasks.length === 0 ? (
          <EmptyContainer>
            <EmptyIcon>
              <InboxOutlined />
            </EmptyIcon>
            <EmptyText>
              {filters.search || filters.status || filters.priority || filters.taskType
                ? t('pages.tasks.noMatchingTasks', '没有找到匹配的任务')
                : t('pages.tasks.noTasks', '暂无任务')}
            </EmptyText>
            {!filters.search && !filters.status && !filters.priority && !filters.taskType && (
              <EmptyAction
                type="primary"
                icon={<PlayCircleOutlined />}
                onClick={() => {
                  // Navigate to create new task
                }}
              >
                {t('pages.tasks.createFirst', '创建第一个任务')}
              </EmptyAction>
            )}
          </EmptyContainer>
        ) : viewMode === 'group' && groupedTasks ? (
          // Grouped View
          <GroupedTasksContainer>
            {groupedTasks.map((group) => (
              <TaskGroup key={group.key}>
                <GroupHeader $color={group.color}>
                  <GroupTitle>{group.label}</GroupTitle>
                  <GroupCount>{group.tasks.length}</GroupCount>
                </GroupHeader>
                <TasksListContainer>
                  {group.tasks.map((task, index) => (
                    <DraggingItem
                      key={task.id}
                      $isDragging={draggedTaskId === task.id}
                      draggable={!filters.status && !filters.priority && !filters.search && !filters.taskType}
                      onDragStart={(e) => handleDragStart(e, task.id)}
                      onDragOver={(e) => handleDragOver(e, filteredAndSortedTasks.indexOf(task))}
                      onDragLeave={handleDragLeave}
                      onDrop={(e) => handleDrop(e, filteredAndSortedTasks.indexOf(task))}
                      onDragEnd={handleDragEnd}
                      ref={(el) => {
                        if (el) {
                          taskItemRefs.current.set(task.id, el);
                        } else {
                          taskItemRefs.current.delete(task.id);
                        }
                      }}
                      style={{
                        animationDelay: `${index * 30}ms`,
                        animation: `${fadeInAnimation} 0.3s ease-out backwards`,
                      }}
                    >
                      {dropTargetIndex === filteredAndSortedTasks.indexOf(task) && draggedTaskId !== task.id && (
                        <DropIndicator />
                      )}
                      <TaskCard
                        task={task}
                        isSelected={cardIsSelected(task)}
                        onSelect={handleCardSelect}
                        onAction={handleTaskAction}
                        viewMode="list"
                        searchHighlight={filters.search}
                      />
                    </DraggingItem>
                  ))}
                </TasksListContainer>
              </TaskGroup>
            ))}
          </GroupedTasksContainer>
        ) : viewMode === 'grid' ? (
          // Grid View
          <TasksGridContainer>
            {filteredAndSortedTasks.map((task, index) => (
              <div
                key={task.id}
                ref={(el) => {
                  if (el) {
                    taskItemRefs.current.set(task.id, el);
                  } else {
                    taskItemRefs.current.delete(task.id);
                  }
                }}
                style={{
                  animationDelay: `${index * 30}ms`,
                  animation: `${fadeInAnimation} 0.3s ease-out backwards`,
                }}
              >
                <TaskCard
                  task={task}
                  isSelected={cardIsSelected(task)}
                  onSelect={handleCardSelect}
                  onAction={handleTaskAction}
                  viewMode="grid"
                  searchHighlight={filters.search}
                />
              </div>
            ))}
          </TasksGridContainer>
        ) : (
          // List View with drag support
          <TasksListContainer>
            {filteredAndSortedTasks.map((task, index) => (
              <DraggingItem
                key={task.id}
                $isDragging={draggedTaskId === task.id}
                draggable={!filters.status && !filters.priority && !filters.search && !filters.taskType}
                onDragStart={(e) => handleDragStart(e, task.id)}
                onDragOver={(e) => handleDragOver(e, index)}
                onDragLeave={handleDragLeave}
                onDrop={(e) => handleDrop(e, index)}
                onDragEnd={handleDragEnd}
                ref={(el) => {
                  if (el) {
                    taskItemRefs.current.set(task.id, el);
                  } else {
                    taskItemRefs.current.delete(task.id);
                  }
                }}
                style={{
                  animationDelay: `${index * 30}ms`,
                  animation: `${fadeInAnimation} 0.3s ease-out backwards`,
                }}
              >
                {dropTargetIndex === index && draggedTaskId !== task.id && (
                  <DropIndicator />
                )}
                <TaskCard
                  task={task}
                  isSelected={cardIsSelected(task)}
                  onSelect={handleCardSelect}
                  onAction={handleTaskAction}
                  viewMode="list"
                  searchHighlight={filters.search}
                />
              </DraggingItem>
            ))}
          </TasksListContainer>
        )}
      </TasksScrollArea>

      {/* Fullscreen Grid View Modal */}
      <FullscreenModal
        open={isFullscreen}
        onCancel={handleCloseFullscreen}
        footer={null}
        width="90vw"
        style={{ top: 20 }}
        title={
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span>{t('pages.tasks.gridFullscreen', '网格视图')}</span>
            <Button
              type="text"
              icon={<FullscreenExitOutlined />}
              onClick={handleCloseFullscreen}
            />
          </div>
        }
      >
        <div style={{ height: '100%', overflow: 'hidden' }}>
          <TasksGridContainer style={{ height: '100%', overflow: 'auto', padding: 16 }}>
            {filteredAndSortedTasks.map((task, index) => (
              <div
                key={task.id}
                style={{
                  animationDelay: `${index * 30}ms`,
                  animation: `${fadeInAnimation} 0.3s ease-out backwards`,
                }}
              >
                <TaskCard
                  task={task}
                  isSelected={fullscreenTask?.id === task.id}
                  onSelect={handleExpandTask}
                  onAction={handleTaskAction}
                  viewMode="grid"
                />
              </div>
            ))}
          </TasksGridContainer>
        </div>
      </FullscreenModal>
    </ListContainer>
  );
};
