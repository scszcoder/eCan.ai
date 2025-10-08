import React from 'react';
import { Input, Button, Dropdown, Tooltip } from 'antd';
import type { MenuProps } from 'antd';
import { SearchOutlined, FilterOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import styled from '@emotion/styled';

const FilterContainer = styled.div`
  padding: 8px;
  background: transparent;
  margin-bottom: 8px;
`;

const FilterRow = styled.div`
  display: flex;
  gap: 8px;
  align-items: center;
`;

export interface TaskFilterOptions {
  status?: string;
  priority?: string;
  trigger?: string;
  search?: string;
  sortBy?: string;
}

interface TaskFiltersProps {
  filters: TaskFilterOptions;
  onChange: (filters: TaskFilterOptions) => void;
}

export const TaskFilters: React.FC<TaskFiltersProps> = ({ filters, onChange }) => {
  const { t } = useTranslation();

  const handleFilterChange = (key: keyof TaskFilterOptions, value: string) => {
    onChange({
      ...filters,
      [key]: value === 'all' ? undefined : value,
    });
  };

  // 优先级菜单项
  const priorityMenuItems: MenuProps['items'] = [
    {
      key: 'all',
      label: t('pages.tasks.filter.allPriorities', '全部优先级'),
    },
    { type: 'divider' },
    {
      key: 'ASAP',
      label: `⚡ ${t('pages.tasks.priority.ASAP', '立即')}`,
    },
    {
      key: 'URGENT',
      label: `🔥 ${t('pages.tasks.priority.URGENT', '紧急')}`,
    },
    {
      key: 'HIGH',
      label: `⬆️ ${t('pages.tasks.priority.HIGH', '高')}`,
    },
    {
      key: 'MID',
      label: `➡️ ${t('pages.tasks.priority.MID', '中')}`,
    },
    {
      key: 'LOW',
      label: `⬇️ ${t('pages.tasks.priority.LOW', '低')}`,
    },
  ];

  // 处理菜单点击
  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    handleFilterChange('priority', key);
  };

  // 获取当前优先级显示文本（用于 Tooltip）
  const getPriorityTooltip = () => {
    const priorityMap: Record<string, string> = {
      ASAP: t('pages.tasks.priority.ASAP', '立即'),
      URGENT: t('pages.tasks.priority.URGENT', '紧急'),
      HIGH: t('pages.tasks.priority.HIGH', '高'),
      MID: t('pages.tasks.priority.MID', '中'),
      LOW: t('pages.tasks.priority.LOW', '低'),
    };
    return filters.priority
      ? `${t('pages.tasks.filter.priority', '优先级')}: ${priorityMap[filters.priority]}`
      : t('pages.tasks.filter.filterByPriority', '筛选优先级');
  };

  return (
    <FilterContainer>
      <FilterRow>
        {/* 搜索框 */}
        <Input
          placeholder={t('pages.tasks.filter.searchPlaceholder', '搜索任务...')}
          prefix={<SearchOutlined />}
          value={filters.search}
          onChange={(e) => handleFilterChange('search', e.target.value)}
          size="small"
          style={{ flex: 1 }}
          allowClear
        />

        {/* 优先级筛选按钮 - 只显示图标 */}
        <Dropdown
          menu={{ items: priorityMenuItems, onClick: handleMenuClick }}
          trigger={['click']}
          placement="bottomRight"
        >
          <Tooltip title={getPriorityTooltip()}>
            <Button
              icon={<FilterOutlined />}
              size="small"
              type={filters.priority ? 'primary' : 'default'}
            />
          </Tooltip>
        </Dropdown>
      </FilterRow>
    </FilterContainer>
  );
};

