import React from 'react';
import { Input, Button, Dropdown, Tag } from 'antd';
import type { MenuProps } from 'antd';
import {
  SearchOutlined,
  FilterOutlined,
  SortDescendingOutlined,
  CheckOutlined,
  AppstoreOutlined,
  DesktopOutlined,
  CloudOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import styled from '@emotion/styled';
import { keyframes, css } from '@emotion/react';

const fadeInAnimation = keyframes`
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
`;

const FilterContainer = styled.div`
  padding: 12px;
  background: rgba(255, 255, 255, 0.02);
  margin-bottom: 8px;
  flex-shrink: 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
`;

const FilterRow = styled.div`
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
`;

const FilterTagsRow = styled.div`
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  animation: ${fadeInAnimation} 0.2s ease-out;
`;

// Quick filter tags container
const QuickFilterTagsContainer = styled.div`
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
`;

const QuickFilterTag = styled.button<{ $isActive?: boolean; $statusColor?: string }>`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 16px;
  font-size: 12px;
  font-weight: 500;
  border: 1px solid ${props => props.$isActive 
    ? (props.$statusColor || 'rgba(59, 130, 246, 0.5)') 
    : 'rgba(255, 255, 255, 0.1)'};
  background: ${props => props.$isActive 
    ? (props.$statusColor ? `${props.$statusColor}20` : 'rgba(59, 130, 246, 0.2)') 
    : 'rgba(255, 255, 255, 0.04)'};
  color: ${props => props.$isActive 
    ? (props.$statusColor || '#60a5fa') 
    : 'var(--text-secondary)'};
  cursor: pointer;
  transition: all 0.2s ease;
  animation: ${fadeInAnimation} 0.2s ease-out;

  &:hover {
    background: ${props => props.$statusColor ? `${props.$statusColor}30` : 'rgba(59, 130, 246, 0.15)'};
    border-color: ${props => props.$statusColor || 'rgba(59, 130, 246, 0.5)'};
    color: ${props => props.$statusColor || '#60a5fa'};
    transform: translateY(-1px);
  }

  &:active {
    transform: translateY(0);
  }
`;

const StatusDot = styled.span<{ $color: string; $pulse?: boolean }>`
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: ${props => props.$color};
  ${props => props.$pulse ? css`
    animation: ${pulseAnimation} 2s ease-in-out infinite;
  ` : ''}
`;

const pulseAnimation = keyframes`
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.6; transform: scale(1.2); }
`;

const StyledInput = styled(Input)`
  &.ant-input-affix-wrapper {
    height: 38px;
    border-radius: 10px;
    background: rgba(51, 65, 85, 0.35);
    border: 1px solid rgba(255, 255, 255, 0.08);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    transition: all 0.3s ease;

    &:hover {
      background: rgba(51, 65, 85, 0.45);
      border-color: rgba(255, 255, 255, 0.12);
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    }

    &:focus,
    &.ant-input-affix-wrapper-focused {
      background: rgba(51, 65, 85, 0.55);
      border-color: rgba(59, 130, 246, 0.5);
      box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15);
    }

    > input.ant-input {
      background: transparent !important;
      border: none !important;
      height: 36px !important;
      line-height: 36px !important;
      padding: 0 !important;
      box-shadow: none !important;
      color: var(--text-primary);
      
      &::placeholder {
        color: var(--text-muted);
      }
    }

    .ant-input-prefix {
      color: rgba(148, 163, 184, 0.6);
      margin-right: 8px;
    }

    .ant-input-suffix {
      color: rgba(148, 163, 184, 0.6);
    }
  }
`;

const FilterButton = styled(Button, {
  shouldForwardProp: (prop) => prop !== '$isActive'
})<{ $isActive?: boolean }>`
  height: 38px !important;
  min-width: 38px !important;
  border-radius: 10px !important;
  background: ${props => props.$isActive 
    ? 'linear-gradient(135deg, rgba(59, 130, 246, 0.9) 0%, rgba(99, 102, 241, 0.9) 100%)' 
    : 'rgba(51, 65, 85, 0.5)'} !important;
  border: 1px solid ${props => props.$isActive 
    ? 'rgba(59, 130, 246, 0.5)' 
    : 'rgba(255, 255, 255, 0.08)'} !important;
  box-shadow: ${props => props.$isActive 
    ? '0 4px 12px rgba(59, 130, 246, 0.3)' 
    : '0 2px 4px rgba(0, 0, 0, 0.1)'} !important;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  padding: 0 12px !important;

  &:hover {
    background: linear-gradient(135deg, rgba(59, 130, 246, 1) 0%, rgba(99, 102, 241, 1) 100%) !important;
    border-color: rgba(59, 130, 246, 0.7) !important;
    box-shadow: 0 6px 16px rgba(59, 130, 246, 0.4) !important;
    transform: translateY(-1px);
  }

  .anticon {
    color: ${props => props.$isActive ? 'white' : 'rgba(59, 130, 246, 0.9)'} !important;
    font-size: 16px !important;
    transition: all 0.3s ease !important;
  }

  &:hover .anticon {
    color: white !important;
  }
`;

const FilterBadgeWrapper = styled.span`
  position: relative;
  display: inline-flex;
  align-items: center;
`;

const ActiveFilterTag = styled(Tag)`
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: 6px;
  font-size: 12px;
  background: rgba(59, 130, 246, 0.15);
  border: 1px solid rgba(59, 130, 246, 0.3);
  color: #60a5fa;
  cursor: pointer;
  transition: all 0.2s ease;
  animation: ${fadeInAnimation} 0.2s ease-out;

  &:hover {
    background: rgba(59, 130, 246, 0.25);
    border-color: rgba(59, 130, 246, 0.5);
  }

  .anticon {
    font-size: 10px;
  }
`;

export interface TaskFilterOptions {
  status?: string;
  priority?: string;
  trigger?: string;
  taskType?: string;
  search?: string;
  sortBy?: string;
  sortOrder?: 'asc' | 'desc';
}

interface TaskFiltersProps {
  filters: TaskFilterOptions;
  onChange: (filters: TaskFilterOptions) => void;
  totalCount?: number;
  filteredCount?: number;
  quickStats?: {
    all: number;
    running: number;
    ready: number;
    pending: number;
    failed: number;
  };
}

export const TaskFilters: React.FC<TaskFiltersProps> = ({ 
  filters, 
  onChange, 
  totalCount = 0,
  quickStats,
}) => {
  const { t } = useTranslation();
  
  // Quick filter statistics
  const displayStats = quickStats || { all: totalCount, running: 0, ready: 0, pending: 0, failed: 0 };

  const handleFilterChange = (key: keyof TaskFilterOptions, value: string | undefined) => {
    onChange({
      ...filters,
      [key]: value === 'all' ? undefined : value,
    });
  };
  
  // Quick filter click handler
  const handleQuickFilter = (status: string | undefined) => {
    if (filters.status === status) {
      handleFilterChange('status', undefined);
    } else {
      handleFilterChange('status', status);
    }
  };

  // Priority Menu Items
  const priorityMenuItems: MenuProps['items'] = [
    {
      key: 'all',
      label: (
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {t('pages.tasks.filter.allPriorities', '全部优先级')}
          {!filters.priority && <CheckOutlined style={{ color: '#52c41a', marginLeft: 'auto' }} />}
        </span>
      ),
    },
    { type: 'divider' },
    {
      key: 'ASAP',
      label: (
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ 
            width: 12, 
            height: 12, 
            borderRadius: '50%', 
            background: '#cf1322',
            display: 'inline-block' 
          }} />
          {t('pages.tasks.priority.ASAP', '立即')}
          {filters.priority === 'ASAP' && <CheckOutlined style={{ color: '#52c41a', marginLeft: 'auto' }} />}
        </span>
      ),
    },
    {
      key: 'URGENT',
      label: (
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ 
            width: 12, 
            height: 12, 
            borderRadius: '50%', 
            background: '#d46b08',
            display: 'inline-block' 
          }} />
          {t('pages.tasks.priority.URGENT', '紧急')}
          {filters.priority === 'URGENT' && <CheckOutlined style={{ color: '#52c41a', marginLeft: 'auto' }} />}
        </span>
      ),
    },
    {
      key: 'HIGH',
      label: (
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ 
            width: 12, 
            height: 12, 
            borderRadius: '50%', 
            background: '#d48806',
            display: 'inline-block' 
          }} />
          {t('pages.tasks.priority.HIGH', '高')}
          {filters.priority === 'HIGH' && <CheckOutlined style={{ color: '#52c41a', marginLeft: 'auto' }} />}
        </span>
      ),
    },
    {
      key: 'MID',
      label: (
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ 
            width: 12, 
            height: 12, 
            borderRadius: '50%', 
            background: '#096dd9',
            display: 'inline-block' 
          }} />
          {t('pages.tasks.priority.MID', '中')}
          {filters.priority === 'MID' && <CheckOutlined style={{ color: '#52c41a', marginLeft: 'auto' }} />}
        </span>
      ),
    },
    {
      key: 'LOW',
      label: (
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ 
            width: 12, 
            height: 12, 
            borderRadius: '50%', 
            background: '#8c8c8c',
            display: 'inline-block' 
          }} />
          {t('pages.tasks.priority.LOW', '低')}
          {filters.priority === 'LOW' && <CheckOutlined style={{ color: '#52c41a', marginLeft: 'auto' }} />}
        </span>
      ),
    },
  ];

  // Status Menu Items
  const statusMenuItems: MenuProps['items'] = [
    {
      key: 'all',
      label: (
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {t('pages.tasks.filter.allStatus', '全部状态')}
          {!filters.status && <CheckOutlined style={{ color: '#52c41a', marginLeft: 'auto' }} />}
        </span>
      ),
    },
    { type: 'divider' },
    {
      key: 'running',
      label: (
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ 
            width: 8, 
            height: 8, 
            borderRadius: '50%', 
            background: '#1890FF',
            animation: 'pulse 2s infinite',
            display: 'inline-block' 
          }} />
          {t('pages.tasks.status.running', '运行中')}
          {filters.status === 'running' && <CheckOutlined style={{ color: '#52c41a', marginLeft: 'auto' }} />}
        </span>
      ),
    },
    {
      key: 'ready',
      label: (
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ 
            width: 8, 
            height: 8, 
            borderRadius: '50%', 
            background: '#52C41A',
            display: 'inline-block' 
          }} />
          {t('pages.tasks.status.ready', '就绪')}
          {filters.status === 'ready' && <CheckOutlined style={{ color: '#52c41a', marginLeft: 'auto' }} />}
        </span>
      ),
    },
    {
      key: 'pending',
      label: (
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ 
            width: 8, 
            height: 8, 
            borderRadius: '50%', 
            background: '#722ed1',
            display: 'inline-block' 
          }} />
          {t('pages.tasks.status.pending', '待处理')}
          {filters.status === 'pending' && <CheckOutlined style={{ color: '#52c41a', marginLeft: 'auto' }} />}
        </span>
      ),
    },
    {
      key: 'completed',
      label: (
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ 
            width: 8, 
            height: 8, 
            borderRadius: '50%', 
            background: '#52C41A',
            display: 'inline-block' 
          }} />
          {t('pages.tasks.status.completed', '已完成')}
          {filters.status === 'completed' && <CheckOutlined style={{ color: '#52c41a', marginLeft: 'auto' }} />}
        </span>
      ),
    },
    {
      key: 'failed',
      label: (
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ 
            width: 8, 
            height: 8, 
            borderRadius: '50%', 
            background: '#FF4D4F',
            display: 'inline-block' 
          }} />
          {t('pages.tasks.status.failed', '失败')}
          {filters.status === 'failed' && <CheckOutlined style={{ color: '#52c41a', marginLeft: 'auto' }} />}
        </span>
      ),
    },
  ];

  // Task Type Menu Items
  const taskTypeMenuItems: MenuProps['items'] = [
    {
      key: 'all',
      label: (
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {t('pages.tasks.filter.allTypes', '全部类型')}
          {!filters.taskType && <CheckOutlined style={{ color: '#52c41a', marginLeft: 'auto' }} />}
        </span>
      ),
    },
    { type: 'divider' },
    {
      key: 'local',
      label: (
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <DesktopOutlined /> {t('pages.tasks.taskType.local', '本地')}
          {filters.taskType === 'local' && <CheckOutlined style={{ color: '#52c41a', marginLeft: 'auto' }} />}
        </span>
      ),
    },
    {
      key: 'cloud',
      label: (
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <CloudOutlined /> {t('pages.tasks.taskType.cloud', '云端')}
          {filters.taskType === 'cloud' && <CheckOutlined style={{ color: '#52c41a', marginLeft: 'auto' }} />}
        </span>
      ),
    },
    {
      key: 'hybrid_cloud',
      label: (
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <CloudOutlined /> {t('pages.tasks.taskType.hybrid_cloud', '混合云')}
          {filters.taskType === 'hybrid_cloud' && <CheckOutlined style={{ color: '#52c41a', marginLeft: 'auto' }} />}
        </span>
      ),
    },
  ];

  const handlePriorityMenuClick: MenuProps['onClick'] = ({ key }) => {
    if (key === 'toggleOrder') {
      onChange({ ...filters, sortOrder: filters.sortOrder === 'asc' ? 'desc' : 'asc' });
    } else {
      handleFilterChange('priority', key);
    }
  };

  const handleStatusMenuClick: MenuProps['onClick'] = ({ key }) => {
    handleFilterChange('status', key);
  };

  const handleTaskTypeMenuClick: MenuProps['onClick'] = ({ key }) => {
    handleFilterChange('taskType', key);
  };

  const clearAllFilters = () => {
    onChange({
      search: '',
      status: undefined,
      priority: undefined,
      taskType: undefined,
      sortBy: 'priority',
      sortOrder: 'desc',
    });
  };

  const getActiveFilterLabel = (key: keyof TaskFilterOptions, value: string) => {
    switch (key) {
      case 'status':
        return t(`pages.tasks.status.${value}`, value);
      case 'priority':
        return t(`pages.tasks.priority.${value}`, value);
      case 'taskType':
        return t(`pages.tasks.taskType.${value}`, value);
      default:
        return value;
    }
  };

  return (
    <FilterContainer>
      {/* Quick Filter Tags */}
      <QuickFilterTagsContainer>
        <QuickFilterTag
          $isActive={!filters.status}
          onClick={() => handleQuickFilter(undefined)}
        >
          全部 <span style={{ opacity: 0.7, marginLeft: 4 }}>{displayStats.all}</span>
        </QuickFilterTag>
        <QuickFilterTag
          $isActive={filters.status === 'running'}
          $statusColor="#1890FF"
          onClick={() => handleQuickFilter('running')}
        >
          <StatusDot $color="#1890FF" $pulse />
          运行中 <span style={{ opacity: 0.7, marginLeft: 4 }}>{displayStats.running}</span>
        </QuickFilterTag>
        <QuickFilterTag
          $isActive={filters.status === 'ready'}
          $statusColor="#52C41A"
          onClick={() => handleQuickFilter('ready')}
        >
          <StatusDot $color="#52C41A" />
          就绪 <span style={{ opacity: 0.7, marginLeft: 4 }}>{displayStats.ready}</span>
        </QuickFilterTag>
        <QuickFilterTag
          $isActive={filters.status === 'pending'}
          $statusColor="#722ed1"
          onClick={() => handleQuickFilter('pending')}
        >
          <StatusDot $color="#722ed1" />
          待处理 <span style={{ opacity: 0.7, marginLeft: 4 }}>{displayStats.pending}</span>
        </QuickFilterTag>
        <QuickFilterTag
          $isActive={filters.status === 'failed'}
          $statusColor="#FF4D4F"
          onClick={() => handleQuickFilter('failed')}
        >
          <StatusDot $color="#FF4D4F" />
          失败 <span style={{ opacity: 0.7, marginLeft: 4 }}>{displayStats.failed}</span>
        </QuickFilterTag>
      </QuickFilterTagsContainer>

      {/* Search and Advanced Filters Row */}
      <FilterRow>
        {/* Search Input */}
        <StyledInput
          placeholder={t('pages.tasks.filter.searchPlaceholder', '搜索任务名称、ID...')}
          prefix={<SearchOutlined />}
          value={filters.search}
          onChange={(e) => handleFilterChange('search', e.target.value)}
          style={{ flex: 1 }}
          allowClear
        />

        {/* Status Filter Button */}
        <Dropdown
          menu={{ items: statusMenuItems, onClick: handleStatusMenuClick }}
          trigger={['click']}
          placement="bottomRight"
        >
          <FilterBadgeWrapper>
            <FilterButton $isActive={!!filters.status}>
              <FilterOutlined />
            </FilterButton>
          </FilterBadgeWrapper>
        </Dropdown>

        {/* Priority Filter Button (also handles sort) */}
        <Dropdown
          menu={{ items: priorityMenuItems, onClick: handlePriorityMenuClick }}
          trigger={['click']}
          placement="bottomRight"
        >
          <FilterBadgeWrapper>
            <FilterButton $isActive={!!filters.priority}>
              <SortDescendingOutlined />
            </FilterButton>
          </FilterBadgeWrapper>
        </Dropdown>

        {/* Task Type Filter Button */}
        <Dropdown
          menu={{ items: taskTypeMenuItems, onClick: handleTaskTypeMenuClick }}
          trigger={['click']}
          placement="bottomRight"
        >
          <FilterBadgeWrapper>
            <FilterButton $isActive={!!filters.taskType}>
              <AppstoreOutlined />
            </FilterButton>
          </FilterBadgeWrapper>
        </Dropdown>
      </FilterRow>

      {/* Active Filters Tags Row */}
      {(filters.status || filters.priority || filters.taskType) && (
        <FilterTagsRow>
          <span style={{ fontSize: 12, color: 'var(--text-muted)', marginRight: 4 }}>
            {t('pages.tasks.filter.activeFilters', '已选筛选')}:
          </span>
          
          {filters.status && (
            <ActiveFilterTag
              closable
              onClose={() => handleFilterChange('status', undefined)}
            >
              {t('pages.tasks.statusLabel', '状态')}: {getActiveFilterLabel('status', filters.status)}
            </ActiveFilterTag>
          )}
          
          {filters.priority && (
            <ActiveFilterTag
              closable
              onClose={() => handleFilterChange('priority', undefined)}
            >
              {t('pages.tasks.priorityLabel', '优先级')}: {getActiveFilterLabel('priority', filters.priority)}
            </ActiveFilterTag>
          )}
          
          {filters.taskType && (
            <ActiveFilterTag
              closable
              onClose={() => handleFilterChange('taskType', undefined)}
            >
              {t('pages.tasks.taskTypeLabel', '类型')}: {getActiveFilterLabel('taskType', filters.taskType)}
            </ActiveFilterTag>
          )}

          <Button 
            type="link" 
            size="small" 
            onClick={clearAllFilters}
            style={{ fontSize: 12, padding: '0 4px', height: 'auto' }}
          >
            {t('pages.tasks.filter.clearAll', '清除全部')}
          </Button>
        </FilterTagsRow>
      )}
    </FilterContainer>
  );
};
