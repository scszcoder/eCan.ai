import React, { useState, useRef, useCallback } from 'react';
import { Input, Button, Dropdown, Tag, Tooltip, List, Divider, Space, Typography, Select } from 'antd';
import { 
    SearchOutlined, 
    FilterOutlined, 
    CloseOutlined, 
    HistoryOutlined,
    ClockCircleOutlined,
    DeleteOutlined,
    MoreOutlined,
    FireOutlined,
    EyeOutlined
} from '@ant-design/icons';
import styled from '@emotion/styled';
import { debounce } from 'lodash-es';
import { useTranslation } from 'react-i18next';

const { Text } = Typography;

// 主Container - 简化Version，去掉边框和内边距
const SearchContainer = styled.div`
  margin-bottom: 0;
  background-color: transparent;
  border: none;
  border-radius: 0;
  padding: 0;
  box-shadow: none;
  transition: var(--transition-normal);
`;

// SearchInput框包装器
const SearchInputWrapper = styled.div`
  position: relative;
  margin-bottom: 0;
  flex: 1;
  min-width: 0;
`;

// SearchInput框 - 与现有Input框风格一致
const StyledInput = styled(Input)`
  &.ant-input-affix-wrapper {
    height: 36px;
    border-radius: 8px;
    background: rgba(51, 65, 85, 0.3);
    border: none;
    color: var(--text-primary);
    font-size: 14px;
    transition: var(--transition-fast);
    padding: 0 12px;
    width: 100%;
    line-height: 36px;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);

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

      &:hover,
      &:focus {
        border: none !important;
        box-shadow: none !important;
        outline: none !important;
      }
    }

    .ant-input-prefix {
      color: rgba(148, 163, 184, 0.7);
      font-size: 14px;
      margin-right: 8px;
    }

    .ant-input-suffix {
      color: rgba(148, 163, 184, 0.7);
      font-size: 12px;
      margin-left: 8px;
      cursor: pointer;
      transition: all 0.3s ease;

      .anticon {
        transition: all 0.3s ease;
      }

      &:hover .anticon {
        color: rgba(248, 250, 252, 0.95);
      }
    }

    .ant-input-clear-icon {
      color: rgba(148, 163, 184, 0.7);
      font-size: 12px;
      
      &:hover {
        color: rgba(248, 250, 252, 0.95);
      }
    }
  }
`;

// OperationButton组
const ActionButtons = styled.div`
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
  flex-shrink: 0;
`;

// OperationButton - 与TaskFilters一致的样式（只Display图标）
const ActionButton = styled(Button)`
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

  &.active {
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

  &.active .anticon {
    color: white !important;
  }
`;

// Search区域Layout
const SearchLayout = styled.div`
  display: flex;
  gap: 8px;
  align-items: flex-start;
`;

// 筛选Tag
const FilterTags = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
`;

// Tag - 与现有Tag风格一致
const FilterTag = styled(Tag)`
  margin: 0;
  padding: 3px 8px;
  border-radius: 6px;
  background-color: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 4px;
  font-weight: 500;
  font-size: 12px;
  transition: var(--transition-fast);

  &:hover {
    background-color: var(--bg-primary);
    border-color: var(--primary-color);
  }

  .anticon {
    font-size: 11px;
    cursor: pointer;
    transition: var(--transition-fast);
    
    &:hover {
      color: #ef4444;
    }
  }
`;

// Search统计
const SearchStats = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background-color: var(--bg-tertiary);
  border-top: 1px solid var(--border-color);
  border-radius: 0 0 12px 12px;
  margin: 0 -12px -12px -12px;
`;

const StatsItem = styled.div`
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--text-secondary);
  font-size: 12px;
`;

// 历史记录下拉Menu
const HistoryDropdown = styled.div`
  max-width: 400px;
  max-height: 300px;
  overflow-y: auto;
`;

const HistoryItem = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  cursor: pointer;
  transition: var(--transition-fast);
  border-radius: 4px;

  &:hover {
    background-color: var(--bg-secondary);
  }

  .history-content {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
    min-width: 0;
  }

  .history-text {
    color: var(--text-primary);
    font-size: 14px;
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .history-time {
    color: var(--text-muted);
    font-size: 12px;
  }

  .history-type {
    display: flex;
    align-items: center;
    gap: 4px;
    color: var(--text-secondary);
    font-size: 12px;
  }

  .history-actions {
    display: flex;
    align-items: center;
    gap: 4px;
    opacity: 0;
    transition: var(--transition-fast);
  }

  &:hover .history-actions {
    opacity: 1;
  }

  .action-btn {
    padding: 2px;
    border-radius: 2px;
    color: var(--text-secondary);
    transition: var(--transition-fast);

    &:hover {
      background-color: var(--bg-tertiary);
      color: #ef4444;
    }
  }
`;

// 筛选下拉Menu
const FilterDropdown = styled.div`
  min-width: 200px;
  max-width: 300px;
`;

const FilterSection = styled.div`
  padding: 8px 0;

  &:not(:last-child) {
    border-bottom: 1px solid var(--border-color);
  }
`;

const FilterSectionTitle = styled.div`
  padding: 8px 12px;
  font-weight: 600;
  color: var(--text-primary);
  font-size: 14px;
  background-color: var(--bg-secondary);
`;

// InterfaceDefinition
interface SearchFilterProps {
  value?: string;
  onSearch: (value: string) => void;
  onFilter?: (filters: Record<string, any>) => void;
  searchHistory?: Array<{ text: string; timestamp: number; type?: 'recent' | 'popular' }>;
  onHistoryClick?: (item: { text: string; timestamp: number; type?: 'recent' | 'popular' }) => void;
  onHistoryDelete?: (item: { text: string; timestamp: number; type?: 'recent' | 'popular' }) => void;
  onHistoryClear?: () => void;
  filterOptions?: {
    key: string;
    label: string;
    options: { label: string; value: any }[];
  }[];
  onFilterReset?: () => void;
  searchStats?: { total: number; filtered: number; time?: number };
  placeholder?: string;
}

const SearchFilter: React.FC<SearchFilterProps> = ({
  value = '',
  onSearch,
  onFilter,
  searchHistory = [],
  onHistoryClick,
  onHistoryDelete,
  onHistoryClear,
  filterOptions = [],
  onFilterReset,
  searchStats,
  placeholder
}) => {
  const { t } = useTranslation();
  const [searchValue, setSearchValue] = useState(value);
  const [activeFilters, setActiveFilters] = useState<Record<string, any>>({});
  const [showHistory, setShowHistory] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const inputRef = useRef<any>(null);

  // 防抖Search
  const debouncedSearch = useCallback(
    debounce((value: string) => {
      onSearch(value);
    }, 300),
    [onSearch]
  );

  // ProcessSearchInput
  const handleSearchInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setSearchValue(value);
    debouncedSearch(value);
  };

  // Process历史记录Click
  const handleHistoryItemClick = (item: { text: string; timestamp: number; type?: 'recent' | 'popular' }) => {
    setSearchValue(item.text);
    onSearch(item.text);
    setShowHistory(false);
    onHistoryClick?.(item);
  };

  // Process历史记录Delete
  const handleHistoryItemDelete = (e: React.MouseEvent, item: { text: string; timestamp: number; type?: 'recent' | 'popular' }) => {
    e.stopPropagation();
    onHistoryDelete?.(item);
  };

  // Process筛选变化
  const handleFilterChange = (key: string, value: any) => {
    const newFilters = { ...activeFilters };
    if (value) {
      newFilters[key] = value;
    } else {
      delete newFilters[key];
    }
    setActiveFilters(newFilters);
    onFilter?.(newFilters);
  };

  // ProcessRemove筛选
  const handleRemoveFilter = (key: string) => {
    const newFilters = { ...activeFilters };
    delete newFilters[key];
    setActiveFilters(newFilters);
    onFilter?.(newFilters);
  };

  // ProcessReset
  const handleReset = () => {
    setActiveFilters({});
    onFilterReset?.();
  };

  // FormatTime
  const formatTime = (timestamp: number) => {
    const now = Date.now();
    const diff = now - timestamp;
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);

    if (minutes < 1) return t('search.justNow');
    if (minutes < 60) return t('search.minutesAgo', { count: minutes });
    if (hours < 24) return t('search.hoursAgo', { count: hours });
    return t('search.daysAgo', { count: days });
  };

  // 历史记录Menu
  const historyMenu = {
    items: [
      ...searchHistory.slice(0, 5).map((item, index) => ({
        key: `history-${index}`,
        label: (
          <HistoryItem onClick={() => handleHistoryItemClick(item)}>
            <div className="history-content">
              <div className="history-type">
                {item.type === 'popular' ? <FireOutlined /> : <ClockCircleOutlined />}
              </div>
              <div className="history-text">{item.text}</div>
              <div className="history-time">{formatTime(item.timestamp)}</div>
            </div>
            <div className="history-actions">
              <Tooltip title={t('search.deleteHistory')}>
                <CloseOutlined 
                  className="action-btn"
                  onClick={(e) => handleHistoryItemDelete(e, item)}
                  aria-label="Delete历史"
                />
              </Tooltip>
            </div>
          </HistoryItem>
        )
      })),
      ...(searchHistory.length > 5 ? [{
        key: 'more-history',
        label: (
          <div style={{ textAlign: 'center', padding: '8px', color: 'var(--text-secondary)' }}>
            {t('search.moreHistory')}
          </div>
        )
      }] : []),
      ...(searchHistory.length > 0 ? [{
        key: 'clear-history',
        label: (
          <div 
            style={{ 
              textAlign: 'center', 
              padding: '8px', 
              color: '#ef4444',
              cursor: 'pointer'
            }}
            onClick={() => {
              onHistoryClear?.();
              setShowHistory(false);
            }}
          >
            {t('search.clearHistory')}
          </div>
        )
      }] : [])
    ]
  };

  // 筛选Menu
  const filterMenu = {
    items: [
      ...filterOptions.map((option, index) => ({
        key: `filter-${index}`,
        label: (
          <FilterSection>
            <FilterSectionTitle>{option.label}</FilterSectionTitle>
            <div style={{ padding: '8px 12px' }}>
              <Select
                id={`filter-select-${option.key}`}
                style={{ width: '100%' }}
                placeholder={t('search.selectFilter', { filter: option.label })}
                value={activeFilters[option.key]}
                onChange={(value) => handleFilterChange(option.key, value)}
                allowClear
                options={option.options}
              />
            </div>
          </FilterSection>
        )
      })),
      ...(filterOptions.length > 0 ? [{
        key: 'filter-reset',
        label: (
          <div 
            style={{ 
              textAlign: 'center', 
              padding: '8px', 
              color: '#ef4444',
              cursor: 'pointer'
            }}
            onClick={() => {
              handleReset();
              setShowFilters(false);
            }}
          >
            {t('search.resetFilters')}
          </div>
        )
      }] : [])
    ]
  };

  return (
    <SearchContainer>
      <SearchLayout>
        <SearchInputWrapper>
          <StyledInput
            ref={inputRef}
            id="chat-search-input"
            value={searchValue}
            onChange={handleSearchInput}
            placeholder={placeholder || t('search.placeholder')}
            prefix={<SearchOutlined />}
            suffix={value && <CloseOutlined onClick={() => {
              setSearchValue('');
              onSearch('');
              // Delay重新聚焦，确保在StatusUpdate后
              setTimeout(() => {
                inputRef.current?.focus();
              }, 0);
            }} />}
            aria-label={t('search.ariaSearch')}
          />
        </SearchInputWrapper>

        <ActionButtons>
          {searchHistory.length > 0 && (
            <Dropdown
              open={showHistory}
              onOpenChange={setShowHistory}
              menu={historyMenu}
              placement="bottomRight"
              trigger={['click']}
            >
              <Tooltip title={t('search.history')}>
                <ActionButton
                  icon={<HistoryOutlined />}
                  onClick={() => setShowHistory(!showHistory)}
                  aria-label={t('search.ariaHistory')}
                  tabIndex={0}
                />
              </Tooltip>
            </Dropdown>
          )}

          {filterOptions.length > 0 && (
            <Dropdown
              open={showFilters}
              onOpenChange={setShowFilters}
              menu={filterMenu}
              placement="bottomRight"
              trigger={['click']}
            >
              <Tooltip title={t('search.filters')}>
                <ActionButton
                  icon={<FilterOutlined />}
                  onClick={() => setShowFilters(!showFilters)}
                  className={Object.keys(activeFilters).length > 0 ? 'active' : ''}
                  aria-label={t('search.ariaFilter')}
                  tabIndex={0}
                />
              </Tooltip>
            </Dropdown>
          )}
        </ActionButtons>
      </SearchLayout>

      {/* 筛选Tag */}
      {Object.keys(activeFilters).length > 0 && (
        <FilterTags>
          {Object.entries(activeFilters).map(([key, value]) => {
            const option = filterOptions.find(opt => opt.key === key);
            const optionItem = option?.options.find(opt => opt.value === value);
            return (
              <FilterTag key={key}>
                {option?.label}{t('search.colon')} {optionItem?.label || value}
                <CloseOutlined onClick={() => handleRemoveFilter(key)} />
              </FilterTag>
            );
          })}
        </FilterTags>
      )}

      {/* Search统计 */}
      {searchStats && (
        <SearchStats>
          <StatsItem>
            <EyeOutlined />
            {t('search.totalResults', { count: searchStats.total })}
          </StatsItem>
          <StatsItem>
            <FilterOutlined />
            {t('search.filteredResults', { count: searchStats.filtered })}
          </StatsItem>
          {searchStats.time && (
            <StatsItem>
              <ClockCircleOutlined />
              {t('search.searchTime', { time: searchStats.time })}
            </StatsItem>
          )}
        </SearchStats>
      )}
    </SearchContainer>
  );
};

export default SearchFilter; 