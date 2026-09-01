import React, { useCallback, useState } from 'react';
import { Input, Popover, Badge, Tooltip } from 'antd';
import { SearchOutlined, FilterOutlined, XOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import styled from '@emotion/styled';

const FilterContainer = styled.div`
  padding: 8px 16px;
  background: transparent;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  flex-shrink: 0;
`;

const FilterTopRow = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: var(--bg-primary);
`;

const SearchInput = styled(Input)`
  flex: 1;
  height: 34px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.08);
  padding: 0 12px 0 12px;
  font-size: 13px;
  color: var(--text-primary);

  &::placeholder {
    color: rgba(255, 255, 255, 0.35);
  }

  &:hover {
    background: rgba(255, 255, 255, 0.08);
    border-color: rgba(255, 255, 255, 0.12);
  }

  &:focus {
    background: rgba(255, 255, 255, 0.08);
    border-color: var(--primary-color);
    box-shadow: 0 0 0 3px rgba(24, 144, 255, 0.15);
  }

  .ant-input {
    font-size: 13px;
    color: var(--text-primary);
    background: transparent;
    &::placeholder {
      color: rgba(255, 255, 255, 0.35);
    }
  }

  .ant-input-prefix {
    margin-right: 0;
  }
`;

const FilterButton = styled.button<{ $active?: boolean }>`
  height: 34px;
  min-width: 34px;
  width: 34px;
  padding: 0;
  border-radius: 8px;
  background: ${props => props.$active 
    ? 'linear-gradient(135deg, #1890ff, #40a9ff)' 
    : 'rgba(255, 255, 255, 0.06)'};
  border: 1px solid ${props => props.$active 
    ? 'rgba(24, 144, 255, 0.5)' 
    : 'rgba(255, 255, 255, 0.08)'};
  color: ${props => props.$active ? 'white' : 'var(--text-secondary)'};
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.2s ease;
  position: relative;
  flex-shrink: 0;

  &:hover {
    background: ${props => props.$active 
      ? 'linear-gradient(135deg, #40a9ff, #69c0ff)' 
      : 'rgba(255, 255, 255, 0.1)'};
    border-color: ${props => props.$active 
      ? 'rgba(24, 144, 255, 0.7)' 
      : 'rgba(255, 255, 255, 0.15)'};
    color: ${props => props.$active ? 'white' : 'var(--text-primary)'};
  }

  .anticon {
    font-size: 14px;
  }
`;

const ActiveFiltersBar = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
`;

const ActiveFilterTag = styled.button<{ $color?: string }>`
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  border-radius: 20px;
  background: ${props => props.$color 
    ? `${props.$color}22` 
    : 'rgba(24, 144, 255, 0.15)'};
  border: 1px solid ${props => props.$color 
    ? `${props.$color}44` 
    : 'rgba(24, 144, 255, 0.3)'};
  color: ${props => props.$color || '#1890ff'};
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: ${props => props.$color 
      ? `${props.$color}33` 
      : 'rgba(24, 144, 255, 0.25)'};
  }

  .anticon {
    font-size: 11px;
  }
`;

const ClearAllBtn = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  border-radius: 20px;
  background: transparent;
  border: 1px solid rgba(245, 34, 45, 0.3);
  color: #ff4d4f;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: rgba(245, 34, 45, 0.1);
    border-color: rgba(245, 34, 45, 0.5);
  }
`;

// Filter Panel Styles
const FilterPanel = styled.div`
  width: 320px;
  padding: 8px 0;
`;

const FilterSection = styled.div`
  padding: 12px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);

  &:last-child {
    border-bottom: none;
  }
`;

const FilterSectionTitle = styled.div`
  font-size: 11px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.4);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 10px;
`;

const FilterOptions = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
`;

const FilterOption = styled.button<{ $selected?: boolean; $color?: string }>`
  padding: 6px 12px;
  border-radius: 8px;
  background: ${props => props.$selected 
    ? (props.$color ? `${props.$color}22` : 'rgba(24, 144, 255, 0.15)') 
    : 'rgba(255, 255, 255, 0.05)'};
  border: 1px solid ${props => props.$selected 
    ? (props.$color ? `${props.$color}55` : 'rgba(24, 144, 255, 0.55)') 
    : 'rgba(255, 255, 255, 0.08)'};
  color: ${props => props.$selected 
    ? (props.$color || '#1890ff') 
    : 'var(--text-secondary)'};
  font-size: 13px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.15s ease;
  font-weight: ${props => props.$selected ? '500' : '400'};

  &:hover {
    background: ${props => props.$selected 
      ? (props.$color ? `${props.$color}33` : 'rgba(24, 144, 255, 0.25)') 
      : 'rgba(255, 255, 255, 0.08)'};
    border-color: ${props => props.$selected 
      ? (props.$color ? `${props.$color}77` : 'rgba(24, 144, 255, 0.7)') 
      : 'rgba(255, 255, 255, 0.15)'};
    color: ${props => props.$selected 
      ? (props.$color || '#1890ff') 
      : 'var(--text-primary)'};
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

const STATUS_CONFIG = [
  { key: 'active', color: '#52c41a', label: 'Active', i18nKey: 'active' },
  { key: 'learning', color: '#1890ff', label: 'Learning', i18nKey: 'learning' },
  { key: 'planned', color: '#8c8c8c', label: 'Planned', i18nKey: 'planned' },
];

const LEVEL_CONFIG = [
  { key: 'entry', color: '#8c8c8c', label: 'Entry', i18nKey: 'pages.skills.levelEntry' },
  { key: 'intermediate', color: '#1890ff', label: 'Intermediate', i18nKey: 'pages.skills.levelIntermediate' },
  { key: 'advanced', color: '#52c41a', label: 'Advanced', i18nKey: 'pages.skills.levelAdvanced' },
];

const SOURCE_CONFIG = [
  { key: 'ui', label: 'My Skills', i18nKey: 'mySkills' },
  { key: 'code', label: 'Code Skills', i18nKey: 'codeSkills' },
  { key: 'subscribed', label: 'Subscribed', i18nKey: 'subscribed' },
  { key: 'marketplace', label: 'Marketplace', i18nKey: 'marketplace' },
];

const PRICE_CONFIG = [
  { key: 'free', color: '#52c41a', label: 'Free', i18nKey: 'free' },
  { key: 'paid', color: '#faad14', label: 'Paid', i18nKey: 'paid' },
];

const SORT_CONFIG = [
    { key: 'trending', label: 'Trending', i18nKey: 'trending' },
    { key: 'downloads', label: 'Most downloaded', i18nKey: 'downloads' },
    { key: 'rating', label: 'Highest rated', i18nKey: 'rating' },
    { key: 'newest', label: 'Newest', i18nKey: 'newest' },
    { key: 'name', label: 'Name', i18nKey: 'name' },
    { key: 'level', label: 'Level', i18nKey: 'level' },
];

export const SkillFilters: React.FC<SkillFiltersProps> = ({ filters, onChange }) => {
  const { t } = useTranslation();
  const [filterPopoverOpen, setFilterPopoverOpen] = useState(false);

  const handleFilterChange = useCallback((key: keyof SkillFilterOptions, value: string) => {
    onChange({
      ...filters,
      [key]: value === 'all' ? undefined : value,
    });
  }, [filters, onChange]);

  const handleFilterToggle = useCallback((key: keyof SkillFilterOptions, value: string) => {
    const currentValue = filters[key];
    if (currentValue === value) {
      // Deselect if already selected
      onChange({ ...filters, [key]: undefined });
    } else {
      onChange({ ...filters, [key]: value });
    }
  }, [filters, onChange]);

  const clearFilter = useCallback((key: keyof SkillFilterOptions) => {
    onChange({ ...filters, [key]: undefined });
  }, [filters, onChange]);

  const clearAllFilters = useCallback(() => {
    onChange({ sortBy: filters.sortBy, search: filters.search });
  }, [filters, onChange]);

  const activeFilterCount = [
    filters.status,
    filters.category,
    filters.source,
    filters.level,
    filters.priceType,
  ].filter(Boolean).length;

  const hasActiveFilters = activeFilterCount > 0;

  // Get translated filter label
  const getTranslatedLabel = (key: string, value: string): string => {
    if (key === 'status') {
      return t(`pages.skills.status.${value}`, STATUS_CONFIG.find(s => s.key === value)?.label || value);
    }
    if (key === 'level') {
      return t(`pages.skills.levels.${value}`, LEVEL_CONFIG.find(l => l.key === value)?.label || value);
    }
    if (key === 'source') {
      return t(`pages.skills.filter.${value}`, SOURCE_CONFIG.find(s => s.key === value)?.label || value);
    }
    if (key === 'priceType') {
      return t(`pages.skills.${value}`, PRICE_CONFIG.find(p => p.key === value)?.label || value);
    }
    return value;
  };

  const getFilterColor = (key: string, value: string): string | undefined => {
    if (key === 'status') {
      return STATUS_CONFIG.find(s => s.key === value)?.color;
    }
    if (key === 'level') {
      return LEVEL_CONFIG.find(l => l.key === value)?.color;
    }
    if (key === 'priceType') {
      return PRICE_CONFIG.find(p => p.key === value)?.color;
    }
    return undefined;
  };

  const renderFilterPanel = () => (
    <FilterPanel>
      <FilterSection>
        <FilterSectionTitle>{t('pages.skills.filter.status', 'Status')}</FilterSectionTitle>
        <FilterOptions>
          {STATUS_CONFIG.map(status => (
            <FilterOption
              key={status.key}
              $selected={filters.status === status.key}
              $color={status.color}
              onClick={() => handleFilterToggle('status', status.key)}
            >
              {t(`pages.skills.status.${status.i18nKey}`, status.label)}
            </FilterOption>
          ))}
        </FilterOptions>
      </FilterSection>

      <FilterSection>
        <FilterSectionTitle>{t('pages.skills.filter.source', 'Source')}</FilterSectionTitle>
        <FilterOptions>
          {SOURCE_CONFIG.map(source => (
            <FilterOption
              key={source.key}
              $selected={filters.source === source.key}
              onClick={() => handleFilterToggle('source', source.key)}
            >
              {t(`pages.skills.filter.${source.i18nKey}`, source.label)}
            </FilterOption>
          ))}
        </FilterOptions>
      </FilterSection>

      <FilterSection>
        <FilterSectionTitle>{t('pages.skills.levels.level', 'Level')}</FilterSectionTitle>
        <FilterOptions>
          {LEVEL_CONFIG.map(level => (
            <FilterOption
              key={level.key}
              $selected={filters.level === level.key}
              $color={level.color}
              onClick={() => handleFilterToggle('level', level.key)}
            >
              {t(`pages.skills.levels.${level.key}`, level.label)}
            </FilterOption>
          ))}
        </FilterOptions>
      </FilterSection>

      <FilterSection>
        <FilterSectionTitle>{t('pages.skills.filter.price', 'Price')}</FilterSectionTitle>
        <FilterOptions>
          {PRICE_CONFIG.map(price => (
            <FilterOption
              key={price.key}
              $selected={filters.priceType === price.key}
              $color={price.color}
              onClick={() => handleFilterToggle('priceType', price.key)}
            >
              {t(`pages.skills.${price.key}`, price.label)}
            </FilterOption>
          ))}
        </FilterOptions>
      </FilterSection>

      <FilterSection>
        <FilterSectionTitle>{t('common.sort', 'Sort By')}</FilterSectionTitle>
        <FilterOptions>
          {SORT_CONFIG.map(sort => (
            <FilterOption
              key={sort.key}
              $selected={filters.sortBy === sort.key}
              onClick={() => handleFilterChange('sortBy', sort.key)}
            >
              {t(`pages.skills.sort.${sort.key}`, sort.label)}
            </FilterOption>
          ))}
        </FilterOptions>
      </FilterSection>
    </FilterPanel>
  );

  return (
    <FilterContainer>
      <FilterTopRow>
        <SearchInput
          placeholder={t('pages.skills.filter.searchPlaceholder', 'Search skills...')}
          prefix={<SearchOutlined style={{ color: 'rgba(255, 255, 255, 0.4)', fontSize: 14, marginLeft: 8 }} />}
          value={filters.search}
          onChange={(e) => handleFilterChange('search', e.target.value)}
          allowClear
        />

        <Popover
          content={renderFilterPanel()}
          trigger="click"
          open={filterPopoverOpen}
          onOpenChange={setFilterPopoverOpen}
          placement="bottomRight"
          styles={{ body: { marginTop: 4 } }}
        >
          <Tooltip title={t('pages.skills.filter.filters', 'Filters')} placement="bottom">
            <FilterButton $active={hasActiveFilters}>
              <FilterOutlined />
              {hasActiveFilters && (
                <Badge
                  count={activeFilterCount}
                  size="small"
                  style={{
                    position: 'absolute',
                    top: -4,
                    right: -4,
                    backgroundColor: '#ff4d4f',
                  }}
                />
              )}
            </FilterButton>
          </Tooltip>
        </Popover>
      </FilterTopRow>

      {hasActiveFilters && (
        <ActiveFiltersBar>
          {filters.status && (
            <ActiveFilterTag
              $color={getFilterColor('status', filters.status)}
              onClick={() => clearFilter('status')}
            >
              {getTranslatedLabel('status', filters.status)}
              <XOutlined />
            </ActiveFilterTag>
          )}
          {filters.source && (
            <ActiveFilterTag
              onClick={() => clearFilter('source')}
            >
              {getTranslatedLabel('source', filters.source)}
              <XOutlined />
            </ActiveFilterTag>
          )}
          {filters.level && (
            <ActiveFilterTag
              $color={getFilterColor('level', filters.level)}
              onClick={() => clearFilter('level')}
            >
              {getTranslatedLabel('level', filters.level)}
              <XOutlined />
            </ActiveFilterTag>
          )}
          {filters.priceType && (
            <ActiveFilterTag
              $color={getFilterColor('priceType', filters.priceType)}
              onClick={() => clearFilter('priceType')}
            >
              {getTranslatedLabel('priceType', filters.priceType)}
              <XOutlined />
            </ActiveFilterTag>
          )}
          <ClearAllBtn onClick={clearAllFilters}>
            <XOutlined style={{ fontSize: 11 }} />
            {t('pages.skills.filter.clearAll', 'Clear')}
          </ClearAllBtn>
        </ActiveFiltersBar>
      )}
    </FilterContainer>
  );
};
