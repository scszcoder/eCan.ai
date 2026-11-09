import React from 'react';
import { Input, Button, Dropdown, Tooltip } from 'antd';
import type { MenuProps } from 'antd';
import { SearchOutlined, FilterOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import styled from '@emotion/styled';

const FilterContainer = styled.div`
  padding: 8px;
  padding-bottom: 12px;
  /* Was a fixed dark-slate literal, which stayed a dark bar in light mode. */
  background: var(--bg-secondary);
  margin-bottom: 8px;
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
  position: sticky;
  top: 0;
  z-index: 10;
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

