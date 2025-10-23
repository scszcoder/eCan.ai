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

// 主容器 - 简化版本，去掉边框和内边距
const SearchContainer = styled.div`
  margin-bottom: 0;
  background-color: transparent;
  border: none;
  border-radius: 0;
  padding: 0;
  box-shadow: none;
  transition: var(--transition-normal);
`;

// 搜索输入框包装器
const SearchInputWrapper = styled.div`
  position: relative;
  margin-bottom: 0;
  flex: 1;
  min-width: 0;
`;

// 搜索输入框 - 与现有输入框风格一致
const StyledInput = styled(Input)`
  height: 36px;
  border-radius: 6px;
  background-color: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  font-size: 14px;
  transition: var(--transition-fast);
  padding: 0 12px 0 36px;
  width: 100%;

  &::placeholder {
    color: var(--text-muted);
  }

  .ant-input-prefix {
    position: absolute;
    left: 12px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--text-secondary);
    font-size: 14px;
    z-index: 2;
  }

  .ant-input-suffix {
    margin-left: 8px;
  }

  /* 确保外层包装器在所有状态下都保持一致的边框 */
  .ant-input-affix-wrapper,
  .ant-input-affix-wrapper:hover,
  .ant-input-affix-wrapper:focus,
  .ant-input-affix-wrapper-focused {
    border-color: var(--border-color) !important;
    box-shadow: none !important;
    outline: none !important;
  }

  /* 确保内部输入框完全没有边框和效果 */
  .ant-input {
    border: none !important;
    box-shadow: none !important;
    outline: none !important;
    background: transparent !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
    
    &:hover,
    &:focus {
      border: none !important;
      box-shadow: none !important;
      outline: none !important;
    }
  }
`;

// 操作按钮组
const ActionButtons = styled.div`
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
  flex-shrink: 0;
`;

// 操作按钮 - 与现有按钮风格一致
const ActionButton = styled(Button)`
  height: 32px;
  border-radius: 6px;
  background-color: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  font-weight: 500;
  transition: var(--transition-fast);
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 0 8px;
  font-size: 13px;

  &:hover {
    background-color: var(--bg-secondary);
    border-color: var(--primary-color);
    color: var(--text-primary);
  }

  &.active {
    background: linear-gradient(90deg, var(--primary-color), var(--accent-color));
    border-color: var(--primary-color);
    color: white;
  }

  .anticon {
    font-size: 13px;
  }
`;

// 搜索区域布局
const SearchLayout = styled.div`
  display: flex;
  gap: 8px;
  align-items: flex-start;
`;

// 筛选标签
const FilterTags = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
`;

// 标签 - 与现有标签风格一致
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

// 搜索统计
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

// 历史记录下拉菜单
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

// 筛选下拉菜单
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

// 接口定义
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

  // 防抖搜索
  const debouncedSearch = useCallback(
    debounce((value: string) => {
      onSearch(value);
    }, 300),
    [onSearch]
  );

  // 处理搜索输入
  const handleSearchInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setSearchValue(value);
    debouncedSearch(value);
  };

  // 处理历史记录点击
  const handleHistoryItemClick = (item: { text: string; timestamp: number; type?: 'recent' | 'popular' }) => {
    setSearchValue(item.text);
    onSearch(item.text);
    setShowHistory(false);
    onHistoryClick?.(item);
  };

  // 处理历史记录删除
  const handleHistoryItemDelete = (e: React.MouseEvent, item: { text: string; timestamp: number; type?: 'recent' | 'popular' }) => {
    e.stopPropagation();
    onHistoryDelete?.(item);
  };

  // 处理筛选变化
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

  // 处理移除筛选
  const handleRemoveFilter = (key: string) => {
    const newFilters = { ...activeFilters };
    delete newFilters[key];
    setActiveFilters(newFilters);
    onFilter?.(newFilters);
  };

  // 处理重置
  const handleReset = () => {
    setActiveFilters({});
    onFilterReset?.();
  };

  // 格式化时间
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

  // 历史记录菜单
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
                  aria-label="删除历史"
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

  // 筛选菜单
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
              // 延迟重新聚焦，确保在状态更新后
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
              <ActionButton
                icon={<HistoryOutlined />}
                onClick={() => setShowHistory(!showHistory)}
                aria-label={t('search.ariaHistory')}
                tabIndex={0}
              >
                {t('search.history')}
              </ActionButton>
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
              <ActionButton
                icon={<FilterOutlined />}
                onClick={() => setShowFilters(!showFilters)}
                className={Object.keys(activeFilters).length > 0 ? 'active' : ''}
                aria-label={t('search.ariaFilter')}
                tabIndex={0}
              >
                {t('search.filters')}
              </ActionButton>
            </Dropdown>
          )}
        </ActionButtons>
      </SearchLayout>

      {/* 筛选标签 */}
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

      {/* 搜索统计 */}
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