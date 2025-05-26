import React, { useState } from 'react';
import { Input, Space, Select, Button, Dropdown, Tag, Tooltip } from 'antd';
import { SearchOutlined, FilterOutlined, ReloadOutlined, CloseOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';

const { Search } = Input;

const FilterContainer = styled.div`
    margin-bottom: 16px;
    background: var(--bg-secondary);
    border-radius: 8px;
    border: 1px solid var(--border-color);
`;

const SearchWrapper = styled.div`
    display: flex;
    align-items: center;
    gap: 12px;
`;

const StyledSearch = styled(Input.Search)`
    width: 100%;

    .ant-input-affix-wrapper {
        height: 32px !important;
        background-color: var(--bg-primary);
        border-color: var(--border-color);
        border-radius: 6px;
        transition: all 0.3s ease;
        padding: 0 4px;

        &:hover, &:focus {
            border-color: var(--primary-color);
            box-shadow: 0 0 0 2px var(--primary-color-light);
        }

        .ant-input {
            height: 30px !important;
            line-height: 30px !important;
            background-color: transparent;
            color: var(--text-primary);
            font-size: 14px;
            padding: 0;
        }

        .anticon {
            color: var(--text-secondary);
            font-size: 14px;
        }

        .ant-input-suffix, .ant-input-prefix {
            margin-right: 4px;
            display: flex;
            align-items: center;
        }
    }

    .ant-input-clear-icon {
        position: absolute;
        right: 20px;
        top: 50%;
        transform: translateY(-50%);
        color: var(--text-secondary);
        z-index: 1;
        padding: 0px;
        cursor: pointer;
        &:hover {
            color: var(--text-primary);
        }
    }

    .ant-input-search-button {
        height: 32px !important;
        background-color: var(--primary-color);
        border-color: var(--primary-color);
        border-radius: 6px;
        transition: all 0.3s ease;

        &:hover {
            background-color: var(--primary-color-hover);
            border-color: var(--primary-color-hover);
        }

        .anticon {
            color: var(--text-primary);
            font-size: 14px;
        }
    }
`;

const FilterButton = styled(Button)`
    height: 24px !important;
    width: 24px !important;
    min-width: 24px !important;
    padding: 0 !important;
    border-radius: 4px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    background-color: var(--bg-primary) !important;
    border-color: var(--border-color) !important;
    color: var(--text-secondary) !important;
    transition: all 0.3s ease !important;

    &:hover {
        background-color: var(--bg-tertiary) !important;
        border-color: var(--primary-color) !important;
        color: var(--primary-color) !important;
    }

    &.active {
        background-color: var(--primary-color-light) !important;
        border-color: var(--primary-color) !important;
        color: var(--primary-color) !important;
    }
`;

const FilterDropdown = styled.div`
    background-color: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 16px;
    min-width: 280px;
    max-height: 400px;
    overflow-y: auto;
`;

const FilterTags = styled.div`
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 12px;
    padding: 0 16px 16px;
`;

const FilterTag = styled(Tag)`
    margin: 0;
    padding: 4px 8px;
    border-radius: 4px;
    background-color: var(--bg-primary);
    border-color: var(--border-color);
    color: var(--text-primary);
    display: flex;
    align-items: center;
    gap: 4px;

    .anticon {
        font-size: 12px;
        cursor: pointer;
        &:hover {
            color: var(--primary-color);
        }
    }
`;

interface SearchFilterProps {
    onSearch: (value: string) => void;
    onFilterChange: (filters: Record<string, any>) => void;
    onReset: () => void;
    filterOptions?: {
        key: string;
        label: string;
        options: { label: string; value: any }[];
    }[];
    placeholder?: string;
}

const SearchFilter: React.FC<SearchFilterProps> = ({
    onSearch,
    onFilterChange,
    onReset,
    filterOptions = [],
    placeholder = 'Search...',
}) => {
    const [filters, setFilters] = useState<Record<string, any>>({});
    const [activeFilters, setActiveFilters] = useState<Record<string, { label: string; value: any }>>({});
    const [searchValue, setSearchValue] = useState('');

    const handleFilterChange = (key: string, value: any) => {
        const newFilters = { ...filters, [key]: value };
        setFilters(newFilters);
        onFilterChange(newFilters);

        if (value) {
            const option = filterOptions.find(opt => opt.key === key)?.options.find(opt => opt.value === value);
            if (option) {
                setActiveFilters(prev => ({ ...prev, [key]: option }));
            }
        } else {
            setActiveFilters(prev => {
                const newActiveFilters = { ...prev };
                delete newActiveFilters[key];
                return newActiveFilters;
            });
        }
    };

    const handleRemoveFilter = (key: string) => {
        handleFilterChange(key, undefined);
    };

    const handleReset = () => {
        setFilters({});
        setActiveFilters({});
        onReset();
    };

    const handleSearch = (value: string) => {
        setSearchValue(value);
        onSearch(value);
    };

    const filterDropdown = (
        <FilterDropdown>
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
                {filterOptions.map(option => (
                    <div key={option.key}>
                        <div style={{ marginBottom: 8, color: 'var(--text-secondary)' }}>{option.label}</div>
                        <Select
                            style={{ width: '100%' }}
                            placeholder={option.label}
                            allowClear
                            value={filters[option.key]}
                            onChange={value => handleFilterChange(option.key, value)}
                            options={option.options}
                        />
                    </div>
                ))}
            </Space>
        </FilterDropdown>
    );

    return (
        <FilterContainer>
            <SearchWrapper>
                <StyledSearch
                    placeholder={placeholder}
                    allowClear
                    value={searchValue}
                    onChange={e => setSearchValue(e.target.value)}
                    onSearch={handleSearch}
                    prefix={
                        <Dropdown
                            overlay={filterDropdown}
                            trigger={['click']}
                            placement="bottomLeft"
                        >
                            <FilterButton
                                icon={<FilterOutlined />}
                                className={Object.keys(activeFilters).length > 0 ? 'active' : ''}
                            />
                        </Dropdown>
                    }
                />
                {Object.keys(activeFilters).length > 0 && (
                    <Tooltip title="Reset all filters">
                        <FilterButton
                            icon={<ReloadOutlined />}
                            onClick={handleReset}
                        />
                    </Tooltip>
                )}
            </SearchWrapper>
            {Object.keys(activeFilters).length > 0 && (
                <FilterTags>
                    {Object.entries(activeFilters).map(([key, filter]) => (
                        <FilterTag
                            key={key}
                            closeIcon={<CloseOutlined />}
                            onClose={() => handleRemoveFilter(key)}
                        >
                            {filter.label}
                        </FilterTag>
                    ))}
                </FilterTags>
            )}
        </FilterContainer>
    );
};

export default SearchFilter; 