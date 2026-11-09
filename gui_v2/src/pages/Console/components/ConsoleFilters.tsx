import React from 'react';
import { Input, Button, Dropdown, Tooltip } from 'antd';
import type { MenuProps } from 'antd';
import { SearchOutlined, FilterOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import styled from '@emotion/styled';

const FilterContainer = styled.div`
  padding: 8px;
  padding-bottom: 12px;
  background: transparent;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
`;

const FilterRow = styled.div`
  display: flex;
  gap: 8px;
  align-items: center;
`;

const StyledInput = styled(Input)`
  &.ant-input-affix-wrapper {
    height: var(--control-height-md);
    border-radius: var(--control-radius);
    background-color: var(--control-bg);
    border: 1px solid var(--border-color);
    box-shadow: var(--shadow-sm);
    transition: background-color 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;

    &:hover {
      background-color: var(--control-bg-hover);
      border-color: var(--primary-border);
    }

    &:focus,
    &.ant-input-affix-wrapper-focused {
      background-color: var(--control-bg-focus);
      border-color: var(--border-color-focus);
      box-shadow: var(--shadow-focus);
    }

    > input.ant-input {
      background: transparent !important;
      border: none !important;
      height: var(--control-height-md) !important;
      line-height: calc(var(--control-height-md) - 2px) !important;
      padding: 0 !important;
      box-shadow: none !important;
      color: var(--text-primary);

      &::placeholder {
        color: var(--text-muted);
      }
    }

    .ant-input-prefix {
      color: var(--text-secondary);
      margin-right: 8px;
    }

    .ant-input-suffix {
      color: var(--text-tertiary);
    }
  }
`;

const StyledFilterButton = styled(Button)`
  height: var(--control-height-md) !important;
  width: 36px !important;
  border-radius: var(--control-radius) !important;
  background: var(--control-bg) !important;
  border: 1px solid var(--border-color) !important;
  box-shadow: var(--shadow-sm) !important;
  transition: background-color 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  padding: 0 !important;

  &:hover {
    background: var(--control-bg-hover) !important;
    border-color: var(--primary-border) !important;
    box-shadow: var(--shadow-md) !important;
  }

  &:active {
    opacity: 0.85 !important;
  }

  &.ant-btn-primary {
    background: var(--primary-fill) !important;
    border-color: var(--primary-color) !important;

    &:hover {
      background: var(--primary-fill-hover) !important;
      border-color: var(--primary-hover) !important;
    }
  }

  .anticon {
    color: var(--primary-text) !important;
    font-size: 16px !important;
    transition: color 0.2s ease !important;
  }

  &:hover .anticon {
    color: var(--primary-color) !important;
  }

  &.ant-btn-primary .anticon {
    color: var(--text-on-primary) !important;
  }
`;

export interface ConsoleFilterOptions {
  status?: string;
  type?: string;
  search?: string;
}

interface ConsoleFiltersProps {
  filters: ConsoleFilterOptions;
  onChange: (filters: ConsoleFilterOptions) => void;
}

export const ConsoleFilters: React.FC<ConsoleFiltersProps> = ({ filters, onChange }) => {
  const { t } = useTranslation();

  const handleFilterChange = (key: keyof ConsoleFilterOptions, value: string) => {
    onChange({
      ...filters,
      [key]: value === 'all' ? undefined : value,
    });
  };

  // StatusMenu项
  const statusMenuItems: MenuProps['items'] = [
    {
      key: 'all',
      label: t('pages.console.filter.allStatus', '全部Status'),
    },
    { type: 'divider' },
    {
      key: 'active',
      label: t('pages.console.status.active', 'Active'),
    },
    {
      key: 'maintenance',
      label: t('pages.console.status.maintenance', 'Maintenance'),
    },
    {
      key: 'offline',
      label: t('pages.console.status.offline', 'Offline'),
    },
  ];

  // TypeMenu项
  const typeMenuItems: MenuProps['items'] = [
    {
      key: 'all',
      label: t('pages.console.filter.allTypes', '全部Type'),
    },
    { type: 'divider' },
    {
      key: 'ground',
      label: t('pages.console.groundVehicle', 'Ground Vehicle'),
    },
    {
      key: 'aerial',
      label: t('pages.console.aerialVehicle', 'Aerial Vehicle'),
    },
  ];

  // ProcessMenuClick
  const handleStatusClick: MenuProps['onClick'] = ({ key }) => {
    handleFilterChange('status', key);
  };

  const handleTypeClick: MenuProps['onClick'] = ({ key }) => {
    handleFilterChange('type', key);
  };

  // GetWhen前筛选Display文本（Used for Tooltip）
  const getFilterTooltip = () => {
    const parts: string[] = [];
    
    if (filters.status) {
      const statusMap: Record<string, string> = {
        active: t('pages.console.status.active', 'Active'),
        maintenance: t('pages.console.status.maintenance', 'Maintenance'),
        offline: t('pages.console.status.offline', 'Offline'),
      };
      parts.push(statusMap[filters.status]);
    }
    
    if (filters.type) {
      const typeMap: Record<string, string> = {
        ground: t('pages.console.groundVehicle', 'Ground Vehicle'),
        aerial: t('pages.console.aerialVehicle', 'Aerial Vehicle'),
      };
      parts.push(typeMap[filters.type]);
    }
    
    return parts.length > 0
      ? parts.join(', ')
      : t('pages.console.filter.filterItems', '筛选项');
  };

  const hasActiveFilters = filters.status || filters.type;

  return (
    <FilterContainer>
      <FilterRow>
        {/* Search框 */}
        <StyledInput
          placeholder={t('pages.console.searchPlaceholder', 'Search...')}
          prefix={<SearchOutlined />}
          value={filters.search}
          onChange={(e) => handleFilterChange('search', e.target.value)}
          style={{ flex: 1 }}
          allowClear
        />

        {/* 筛选Button - 只Display图标，Support多级Menu */}
        <Dropdown
          menu={{ 
            items: [
              {
                key: 'status',
                label: t('pages.console.statusLabel', 'Status'),
                children: statusMenuItems,
              },
              {
                key: 'type',
                label: t('pages.console.type', 'Type'),
                children: typeMenuItems,
              },
            ],
            onClick: (info) => {
              // 根据父级key判断是哪个筛选项
              const keyPath = info.keyPath;
              if (keyPath.length > 1) {
                const filterType = keyPath[1]; // 'status' 或 'type'
                const value = keyPath[0];
                handleFilterChange(filterType as keyof ConsoleFilterOptions, value);
              }
            }
          }}
          trigger={['click']}
          placement="bottomRight"
        >
          <Tooltip title={getFilterTooltip()}>
            <StyledFilterButton
              icon={<FilterOutlined />}
              type={hasActiveFilters ? 'primary' : 'default'}
            />
          </Tooltip>
        </Dropdown>
      </FilterRow>
    </FilterContainer>
  );
};

