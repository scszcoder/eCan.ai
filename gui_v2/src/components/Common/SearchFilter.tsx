import React from 'react';
import { Input, Space, Select, Button } from 'antd';
import { SearchOutlined, FilterOutlined, ReloadOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';

const { Search } = Input;

const FilterContainer = styled.div`
    margin-bottom: 16px;
    padding: 16px;
    background: #fafafa;
    border-radius: 8px;
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
            <Space style={{ width: '100%' }} size="middle">
                <Search
                    placeholder={placeholder}
                    allowClear
                    onSearch={onSearch}
                    style={{ width: 300 }}
                    prefix={<SearchOutlined />}
                />
                {filterOptions.map(option => (
                    <Select
                        key={option.key}
                        placeholder={option.label}
                        style={{ width: 200 }}
                        allowClear
                        onChange={value => handleFilterChange(option.key, value)}
                        options={option.options}
                    />
                ))}
                <Button 
                    icon={<ReloadOutlined />} 
                    onClick={onReset}
                >
                    Reset
                </Button>
            </Space>
        </FilterContainer>
    );
};

export default SearchFilter; 