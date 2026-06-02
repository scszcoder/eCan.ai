import React, { useMemo, useCallback } from 'react';
import { Input, Button, Dropdown, Tooltip } from 'antd';
import type { MenuProps } from 'antd';
import { SearchOutlined, FilterOutlined, DownOutlined } from '@ant-design/icons';
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

const FilterRowSecond = styled.div`
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 8px;
  flex-wrap: wrap;
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

export interface SkillFilterOptions {
  status?: string;
  category?: string;
  search?: string;
  sortBy?: string;
  source?: string;
  level?: string;
  priceType?: string;
}

interface SkillFiltersProps {
  filters: SkillFilterOptions;
  onChange: (filters: SkillFilterOptions) => void;
}

export const SkillFilters: React.FC<SkillFiltersProps> = ({ filters, onChange }) => {
  const { t } = useTranslation();

  const handleFilterChange = useCallback((key: keyof SkillFilterOptions, value: string) => {
    onChange({
      ...filters,
      [key]: value === 'all' ? undefined : value,
    });
  }, [filters, onChange]);

  // Status menu items - memoized to prevent unnecessary re-renders
  const statusMenuItems = useMemo<MenuProps['items']>(() => [
    {
      key: 'all',
      label: t('pages.skills.filter.allStatus'),
    },
    { type: 'divider' },
    {
      key: 'active',
      label: t('pages.skills.status.active'),
    },
    {
      key: 'learning',
      label: t('pages.skills.status.learning'),
    },
    {
      key: 'planned',
      label: t('pages.skills.status.planned'),
    },
  ], [t]);

  // Process menu click
  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    handleFilterChange('status', key);
  };

  // Source filter menu items - memoized
  const sourceMenuItems = useMemo<MenuProps['items']>(() => [
    { key: 'all', label: t('pages.skills.filter.allSources') },
    { type: 'divider' },
    { key: 'ui', label: t('pages.skills.filter.mySkills') },
    { key: 'code', label: t('pages.skills.filter.codeSkills') },
    { key: 'subscribed', label: t('pages.skills.filter.subscribed') },
  ], [t]);

  // Level filter menu items - memoized
  const levelMenuItems = useMemo<MenuProps['items']>(() => [
    { key: 'all', label: t('pages.skills.filter.allLevels') },
    { type: 'divider' },
    { key: 'entry', label: t('pages.skills.levels.entry') },
    { key: 'intermediate', label: t('pages.skills.levels.intermediate') },
    { key: 'advanced', label: t('pages.skills.levels.advanced') },
  ], [t]);

  // Price type filter menu items - memoized
  const priceTypeMenuItems = useMemo<MenuProps['items']>(() => [
    { key: 'all', label: t('pages.skills.filter.allPrices') },
    { type: 'divider' },
    { key: 'free', label: t('pages.skills.free') },
    { key: 'paid', label: t('pages.skills.paid') },
  ], [t]);

  // Handle source filter
  const handleSourceMenuClick: MenuProps['onClick'] = ({ key }) => {
    handleFilterChange('source', key);
  };

  // Handle level filter
  const handleLevelMenuClick: MenuProps['onClick'] = ({ key }) => {
    handleFilterChange('level', key);
  };

  // Handle price type filter
  const handlePriceTypeMenuClick: MenuProps['onClick'] = ({ key }) => {
    handleFilterChange('priceType', key);
  };

  // Get current status display text (used for tooltip)
  const getStatusTooltip = () => {
    const statusMap: Record<string, string> = {
      active: t('pages.skills.status.active'),
      learning: t('pages.skills.status.learning'),
      planned: t('pages.skills.status.planned'),
    };
    return filters.status
      ? `${t('pages.skills.filter.status')}: ${statusMap[filters.status]}`
      : t('pages.skills.filter.filterByStatus');
  };

  return (
    <FilterContainer>
      <FilterRow>
        {/* Search box */}
        <StyledInput
          placeholder={t('pages.skills.filter.searchPlaceholder')}
          prefix={<SearchOutlined />}
          value={filters.search}
          onChange={(e) => handleFilterChange('search', e.target.value)}
          style={{ flex: 1 }}
          allowClear
        />

        {/* Status filter button - only display icon */}
        <Dropdown
          menu={{ items: statusMenuItems, onClick: handleMenuClick }}
          trigger={['click']}
          placement="bottomRight"
        >
          <Tooltip title={getStatusTooltip()}>
            <StyledFilterButton
              icon={<FilterOutlined />}
              type={filters.status ? 'primary' : 'default'}
            />
          </Tooltip>
        </Dropdown>
      </FilterRow>

      <FilterRowSecond>
        {/* Source filter */}
        <Dropdown
          menu={{ items: sourceMenuItems, onClick: handleSourceMenuClick }}
          trigger={['click']}
          placement="bottomLeft"
        >
          <Button
            size="small"
            style={{
              background: filters.source && filters.source !== 'all' ? 'rgba(24, 144, 255, 0.15)' : 'rgba(51, 65, 85, 0.3)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              color: filters.source && filters.source !== 'all' ? '#1890ff' : 'rgba(255, 255, 255, 0.7)',
              borderRadius: 6,
              height: 28,
              fontSize: 12,
            }}
          >
            {t('pages.skills.filter.source')} <DownOutlined style={{ marginLeft: 4, fontSize: 10 }} />
          </Button>
        </Dropdown>

        {/* Level filter */}
        <Dropdown
          menu={{ items: levelMenuItems, onClick: handleLevelMenuClick }}
          trigger={['click']}
          placement="bottomLeft"
        >
          <Button
            size="small"
            style={{
              background: filters.level && filters.level !== 'all' ? 'rgba(24, 144, 255, 0.15)' : 'rgba(51, 65, 85, 0.3)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              color: filters.level && filters.level !== 'all' ? '#1890ff' : 'rgba(255, 255, 255, 0.7)',
              borderRadius: 6,
              height: 28,
              fontSize: 12,
            }}
          >
            {t('pages.skills.levels.level')} <DownOutlined style={{ marginLeft: 4, fontSize: 10 }} />
          </Button>
        </Dropdown>

        {/* Price type filter */}
        <Dropdown
          menu={{ items: priceTypeMenuItems, onClick: handlePriceTypeMenuClick }}
          trigger={['click']}
          placement="bottomLeft"
        >
          <Button
            size="small"
            style={{
              background: filters.priceType && filters.priceType !== 'all' ? 'rgba(24, 144, 255, 0.15)' : 'rgba(51, 65, 85, 0.3)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              color: filters.priceType && filters.priceType !== 'all' ? '#1890ff' : 'rgba(255, 255, 255, 0.7)',
              borderRadius: 6,
              height: 28,
              fontSize: 12,
            }}
          >
            {t('pages.skills.filter.price')} <DownOutlined style={{ marginLeft: 4, fontSize: 10 }} />
          </Button>
        </Dropdown>
      </FilterRowSecond>
    </FilterContainer>
  );
};

