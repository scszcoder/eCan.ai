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
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
`;

const FilterRow = styled.div`
  display: flex;
  gap: 8px;
  align-items: center;
`;

const StyledInput = styled(Input)`
  &.ant-input-affix-wrapper {
    height: 36px;
    border-radius: 8px;
    background: rgba(51, 65, 85, 0.3);
    border: none;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    transition: all 0.3s ease;

    &:hover {
      background: rgba(51, 65, 85, 0.4);
      box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
    }

    &:focus,
    &.ant-input-affix-wrapper-focused {
      background: rgba(51, 65, 85, 0.5);
      box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
    }

    > input.ant-input {
      background: transparent !important;
      border: none !important;
      height: 34px !important;
      line-height: 34px !important;
      padding: 0 !important;
      box-shadow: none !important;
      color: var(--text-primary);
      
      &::placeholder {
        color: var(--text-muted);
      }
    }

    .ant-input-prefix {
      color: rgba(148, 163, 184, 0.7);
      margin-right: 8px;
    }

    .ant-input-suffix {
      color: rgba(148, 163, 184, 0.7);
    }
  }
`;

const StyledFilterButton = styled(Button)`
  height: 36px !important;
  width: 36px !important;
  border-radius: 8px !important;
  background: rgba(51, 65, 85, 0.5) !important;
  border: 1px solid rgba(255, 255, 255, 0.08) !important;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1) !important;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  padding: 0 !important;

  &:hover {
    background: rgba(51, 65, 85, 0.7) !important;
    border-color: rgba(59, 130, 246, 0.3) !important;
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15) !important;
  }

  &:active {
    opacity: 0.8 !important;
  }

  &.ant-btn-primary {
    background: linear-gradient(135deg, rgba(59, 130, 246, 0.9) 0%, rgba(99, 102, 241, 0.9) 100%) !important;
    border-color: rgba(59, 130, 246, 0.5) !important;
    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3) !important;

    &:hover {
      background: linear-gradient(135deg, rgba(59, 130, 246, 1) 0%, rgba(99, 102, 241, 1) 100%) !important;
      border-color: rgba(59, 130, 246, 0.7) !important;
      box-shadow: 0 6px 16px rgba(59, 130, 246, 0.4) !important;
    }
  }

  .anticon {
    color: rgba(59, 130, 246, 0.9) !important;
    font-size: 16px !important;
    transition: all 0.3s ease !important;
  }

  &:hover .anticon {
    color: rgba(96, 165, 250, 1) !important;
  }

  &.ant-btn-primary .anticon {
    color: white !important;
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
                label: t('pages.console.status', 'Status'),
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

