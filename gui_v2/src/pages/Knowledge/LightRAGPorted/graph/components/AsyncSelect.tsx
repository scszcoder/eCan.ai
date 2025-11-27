import React, { useState, useCallback, useEffect, useRef } from 'react';
import { Select, Spin, Input } from 'antd';
import { SearchOutlined, DownOutlined } from '@ant-design/icons';
import type { SelectProps } from 'antd';

interface AsyncSelectProps<T> {
  fetcher: (query?: string) => Promise<T[]>;
  renderOption: (item: T) => React.ReactNode;
  getOptionValue: (item: T) => string;
  getDisplayValue: (item: T) => React.ReactNode;
  value?: string | null;
  onChange: (value: string) => void;
  onFocus?: (value: string | null) => void;
  onBeforeOpen?: () => Promise<void>;
  placeholder?: string;
  searchPlaceholder?: string;
  noResultsMessage?: string;
  notFound?: React.ReactNode;
  ariaLabel?: string;
  className?: string;
  triggerClassName?: string;
  searchInputClassName?: string;
  triggerTooltip?: string;
  clearable?: boolean;
  debounceTime?: number;
}

export function AsyncSelect<T>({
  fetcher,
  renderOption,
  getOptionValue,
  getDisplayValue,
  value,
  onChange,
  onFocus,
  onBeforeOpen,
  placeholder = '请选择...',
  searchPlaceholder = '搜索节点名称...',
  noResultsMessage = '无结果',
  notFound,
  ariaLabel,
  className,
  debounceTime = 300,
  clearable = true
}: AsyncSelectProps<T>) {
  const [options, setOptions] = useState<T[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchValue, setSearchValue] = useState('');
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);

  // 加载选项数据
  const loadOptions = useCallback(async (query?: string) => {
    setLoading(true);
    try {
      const results = await fetcher(query);
      setOptions(results);
    } catch (error) {
      console.error('Error loading options:', error);
      setOptions([]);
    } finally {
      setLoading(false);
    }
  }, [fetcher]);

  // 初始加载
  useEffect(() => {
    loadOptions();
  }, [loadOptions]);

  // 处理搜索
  const handleSearch = useCallback((query: string) => {
    setSearchValue(query);
    
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    debounceTimerRef.current = setTimeout(() => {
      loadOptions(query);
    }, debounceTime);
  }, [loadOptions, debounceTime]);

  // 处理下拉框打开
  const handleDropdownVisibleChange = useCallback(async (open: boolean) => {
    if (open && onBeforeOpen) {
      await onBeforeOpen();
      // 重新加载数据
      await loadOptions(searchValue);
    }
  }, [onBeforeOpen, loadOptions, searchValue]);

  // 处理选择
  const handleChange = useCallback((val: string) => {
    onChange(val);
    setSearchValue('');
  }, [onChange]);

  // 处理焦点
  const handleFocus = useCallback(() => {
    if (onFocus && value) {
      onFocus(value);
    }
  }, [onFocus, value]);

  // 清理定时器
  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, []);

  // 转换选项为 Ant Design Select 格式
  const selectOptions: SelectProps['options'] = options.map((item) => ({
    value: getOptionValue(item),
    label: renderOption(item)
  }));

  // 自定义下拉渲染，在顶部添加搜索框
  const popupRender = (menu: React.ReactElement) => (
    <>
      <div style={{ padding: '8px 8px 4px 8px' }}>
        <Input
          prefix={<SearchOutlined style={{ color: 'rgba(255, 255, 255, 0.6)' }} />}
          placeholder={searchPlaceholder}
          value={searchValue}
          onChange={(e) => handleSearch(e.target.value)}
          style={{
            background: 'rgba(100, 116, 139, 0.3)',
            border: '1px solid rgba(255, 255, 255, 0.15)',
            borderRadius: 8,
            color: '#ffffff'
          }}
          className="async-select-search-input"
        />
      </div>
      {menu}
    </>
  );

  return (
    <Select
      value={value || undefined}
      placeholder={placeholder}
      onChange={handleChange}
      onFocus={handleFocus}
      onOpenChange={handleDropdownVisibleChange}
      loading={loading}
      allowClear={clearable}
      filterOption={false}
      notFoundContent={loading ? <Spin size="small" /> : (notFound || noResultsMessage)}
      className={`${className} graph-async-select`}
      popupRender={popupRender}
      // Use Ant Design v5 classNames API instead of deprecated popupClassName
      // @ts-ignore
      classNames={{ popup: 'lightrag-async-select-dropdown' }}
      aria-label={ariaLabel}
      suffixIcon={<DownOutlined style={{ color: 'rgba(255, 255, 255, 0.6)' }} />}
      style={{ 
        width: '100%',
        background: 'rgba(100, 116, 139, 0.5)',
        borderRadius: 999,
        border: '1px solid rgba(255, 255, 255, 0.15)',
        color: '#ffffff',
        height: 40
      }}
      // @ts-ignore - Antd v5 new API
      styles={{
        popup: {
          borderRadius: 12,
          boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
          backgroundColor: 'rgba(45, 55, 72, 0.95)',
          backdropFilter: 'blur(12px)',
          border: '2px solid rgba(255, 255, 255, 0.1)',
        } as any,
      }}
      options={selectOptions}
    />
  );
}

export default AsyncSelect;
