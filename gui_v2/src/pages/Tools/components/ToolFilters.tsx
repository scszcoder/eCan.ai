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

export interface ToolFilterOptions {
  category?: string;
  search?: string;
}

interface ToolFiltersProps {
  filters: ToolFilterOptions;
  onChange: (filters: ToolFilterOptions) => void;
}

export const ToolFilters: React.FC<ToolFiltersProps> = ({ filters, onChange }) => {
  const { t } = useTranslation();

  const handleFilterChange = (key: keyof ToolFilterOptions, value: string) => {
    onChange({
      ...filters,
      [key]: value === 'all' ? undefined : value,
    });
  };

  // 类别Menu项
  const categoryMenuItems: MenuProps['items'] = [
    {
      key: 'all',
      label: t('pages.tools.filter.allCategories', '全部类别'),
    },
    { type: 'divider' },
    {
      key: 'system',
      label: t('pages.tools.category.system', 'SystemTool'),
    },
    {
      key: 'custom',
      label: t('pages.tools.category.custom', 'CustomTool'),
    },
  ];

  // ProcessMenuClick
  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    handleFilterChange('category', key);
  };

  // GetWhen前类别Display文本（Used for Tooltip）
  const getCategoryTooltip = () => {
    const categoryMap: Record<string, string> = {
      system: t('pages.tools.category.system', 'SystemTool'),
      custom: t('pages.tools.category.custom', 'CustomTool'),
    };
    return filters.category
      ? `${t('pages.tools.filter.category', '类别')}: ${categoryMap[filters.category]}`
      : t('pages.tools.filter.filterByCategory', '筛选类别');
  };

  return (
    <FilterContainer>
      <FilterRow>
        {/* Search框 */}
        <StyledInput
          placeholder={t('pages.tools.filter.searchPlaceholder', 'SearchTool...')}
          prefix={<SearchOutlined />}
          value={filters.search}
          onChange={(e) => handleFilterChange('search', e.target.value)}
          style={{ flex: 1 }}
          allowClear
        />

        {/* 类别筛选Button - 只Display图标 */}
        <Dropdown
          menu={{ items: categoryMenuItems, onClick: handleMenuClick }}
          trigger={['click']}
          placement="bottomRight"
        >
          <Tooltip title={getCategoryTooltip()}>
            <StyledFilterButton
              icon={<FilterOutlined />}
              type={filters.category ? 'primary' : 'default'}
            />
          </Tooltip>
        </Dropdown>
      </FilterRow>
    </FilterContainer>
  );
};

