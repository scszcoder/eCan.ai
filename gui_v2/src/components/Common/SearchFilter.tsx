import React from 'react';
import { Input, Space, Select, Button } from 'antd';
import { SearchOutlined, FilterOutlined, ReloadOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';

const { Search } = Input;

const FilterContainer = styled.div`
    margin-bottom: 16px;
    padding: 16px;
    background: var(--bg-secondary);
    border-radius: 8px;
    border: 1px solid var(--border-color);
`;

const StyledSearch = styled(Search)`
    .ant-input-affix-wrapper {
        background-color: var(--bg-primary);
        border-color: var(--border-color);
        &:hover, &:focus {
            border-color: var(--primary-color);
        }
    }
    .ant-input {
        background-color: var(--bg-primary);
        color: var(--text-primary);
        &::placeholder {
            color: var(--text-secondary);
        }
    }
    .ant-input-search-button {
        background-color: var(--primary-color);
        border-color: var(--primary-color);
        &:hover {
            background-color: var(--primary-color-hover);
            border-color: var(--primary-color-hover);
        }
    }
`;

const StyledSelect = styled(Select)`
    .ant-select-selector {
        background-color: var(--bg-primary) !important;
        border-color: var(--border-color) !important;
        &:hover {
            border-color: var(--primary-color) !important;
        }
    }
    .ant-select-selection-item {
        color: var(--text-primary) !important;
    }
    .ant-select-arrow {
        color: var(--text-secondary);
    }
`;

const StyledButton = styled(Button)`
    &.ant-btn {
        background-color: var(--bg-primary);
        border-color: var(--border-color);
        color: var(--text-primary);
        &:hover {
            background-color: var(--bg-tertiary);
            border-color: var(--primary-color);
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
    const handleFilterChange = (key: string, value: any) => {
        onFilterChange({ [key]: value });
    };

    return (
        <FilterContainer>
            <Space style={{ width: '100%' }} size="middle" wrap>
                <StyledSearch
                    placeholder={placeholder}
                    allowClear
                    onSearch={onSearch}
                    style={{ minWidth: 300, flex: 1 }}
                    prefix={<SearchOutlined />}
                />
                {filterOptions.map(option => (
                    <StyledSelect
                        key={option.key}
                        placeholder={option.label}
                        style={{ minWidth: 200 }}
                        allowClear
                        onChange={value => handleFilterChange(option.key, value)}
                        options={option.options}
                    />
                ))}
                <StyledButton 
                    icon={<ReloadOutlined />} 
                    onClick={onReset}
                >
                    Reset
                </StyledButton>
            </Space>
        </FilterContainer>
    );
};

export default SearchFilter; 