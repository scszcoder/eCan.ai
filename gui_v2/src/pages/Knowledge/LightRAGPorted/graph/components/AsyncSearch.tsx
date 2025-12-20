import React, { useState, useCallback, useEffect, useRef } from 'react';
import { Input } from 'antd';
import { Search } from 'lucide-react';

interface AsyncSearchProps<T> {
  fetcher: (query?: string) => Promise<T[]>;
  renderOption: (item: T) => React.ReactNode;
  getOptionValue: (item: T) => string;
  value?: string | null;
  onChange?: (value: string | null) => void;
  onFocus?: (value: string | null) => void;
  placeholder?: string;
  ariaLabel?: string;
  noResultsMessage?: string;
  className?: string;
}

function AsyncSearch<T>({
  fetcher,
  renderOption,
  getOptionValue,
  value,
  onChange,
  onFocus,
  placeholder,
  ariaLabel,
  noResultsMessage,
  className
}: AsyncSearchProps<T>) {
  const [query, setQuery] = useState('');
  const [options, setOptions] = useState<T[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const loadOptions = useCallback(async (searchQuery: string) => {
    setIsLoading(true);
    try {
      const results = await fetcher(searchQuery);
      setOptions(results);
    } catch (error) {
      console.error('Error loading options:', error);
      setOptions([]);
    } finally {
      setIsLoading(false);
    }
  }, [fetcher]);

  useEffect(() => {
    if (isOpen) {
      loadOptions(query);
    }
  }, [query, isOpen, loadOptions]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setQuery(e.target.value);
    setIsOpen(true);
  };

  const handleOptionClick = (item: T) => {
    const optionValue = getOptionValue(item);
    onChange?.(optionValue);
    setIsOpen(false);
    setQuery('');
  };

  const handleOptionHover = (item: T) => {
    const optionValue = getOptionValue(item);
    onFocus?.(optionValue);
  };

  return (
    <div ref={containerRef} className={className} style={{ position: 'relative', width: '100%' }}>
      <Input
        prefix={<Search size={16} style={{ color: 'rgba(255, 255, 255, 0.6)' }} />}
        value={query}
        onChange={handleInputChange}
        onFocus={() => setIsOpen(true)}
        placeholder={placeholder}
        aria-label={ariaLabel}
        style={{
          borderRadius: 999,
          background: 'rgba(100, 116, 139, 0.5)',
          backdropFilter: 'blur(12px)',
          border: '1px solid rgba(255, 255, 255, 0.15)',
          color: '#ffffff',
          fontSize: 14,
          height: 40
        }}
        className="graph-search-input"
      />
      
      {isOpen && (
        <div style={{
          position: 'absolute',
          top: '100%',
          left: 0,
          right: 0,
          marginTop: 4,
          background: 'rgba(45, 55, 72, 0.95)',
          border: '2px solid rgba(255, 255, 255, 0.1)',
          borderRadius: 8,
          boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
          backdropFilter: 'blur(12px)',
          maxHeight: 300,
          overflowY: 'auto',
          zIndex: 1000,
          color: '#ffffff'
        }}>
          {isLoading ? (
            <div style={{ padding: 12, textAlign: 'center', color: '#999' }}>加载中...</div>
          ) : options.length === 0 ? (
            <div style={{ padding: 12, textAlign: 'center', color: '#999' }}>
              {noResultsMessage || '无结果'}
            </div>
          ) : (
            options.map((item, index) => (
              <div
                key={index}
                onClick={() => handleOptionClick(item)}
                onMouseEnter={() => handleOptionHover(item)}
                onMouseLeave={() => onFocus?.(null)}
                style={{
                  padding: '8px 12px',
                  cursor: 'pointer',
                  transition: 'background 0.2s'
                }}
                onMouseOver={(e) => e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)'}
                onMouseOut={(e) => e.currentTarget.style.background = 'transparent'}
              >
                {renderOption(item)}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

export default AsyncSearch;
