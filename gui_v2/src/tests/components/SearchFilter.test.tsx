import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { act } from 'react';
import '@testing-library/jest-dom';
import SearchFilter from '../../components/Common/SearchFilter';
import { 
  mockArticles, 
  mockSearchHistory, 
  mockFilterOptions, 
  mockUtils,
  MockHistoryItem 
} from '../__mocks__/searchFilterMockData';

// Mock i18next
jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, params?: Record<string, any>) => {
      const translations: Record<string, string> = {
        'search.placeholder': 'Search文章、Tag、作者...',
        'search.clear': '清除',
        'search.history': '历史',
        'search.filters': '筛选',
        'search.deleteHistory': 'Delete历史',
        'search.clearHistory': '清空历史',
        'search.moreHistory': '更多历史',
        'search.resetFilters': 'Reset筛选',
        'search.selectFilter': `Select${params?.filter || ''}`,
        'search.totalResults': `共 ${params?.count || 0} 项`,
        'search.filteredResults': `筛选出 ${params?.count || 0} 项`,
        'search.searchTime': `耗时 ${params?.time || 0}ms`,
        'search.justNow': '刚刚',
        'search.minutesAgo': `${params?.count || 0} 分钟前`,
        'search.hoursAgo': `${params?.count || 0} 小时前`,
        'search.daysAgo': `${params?.count || 0} 天前`,
        'search.ariaSearch': 'Search',
        'search.ariaHistory': '查看Search历史',
        'search.ariaFilter': 'Open筛选选项',
        'search.colon': '：'
      };
      return translations[key] || key;
    }
  })
}));

// Mock lodash-es debounce
jest.mock('lodash-es', () => ({
  debounce: (fn: Function) => fn
}));

describe('SearchFilter Component', () => {
  const defaultProps = {
    onSearch: jest.fn(),
    onFilter: jest.fn(),
    searchHistory: mockSearchHistory,
    onHistoryClick: jest.fn(),
    onHistoryDelete: jest.fn(),
    onHistoryClear: jest.fn(),
    filterOptions: mockFilterOptions,
    onFilterReset: jest.fn(),
    searchStats: { total: 10, filtered: 10, time: 50 },
    placeholder: 'Search文章、Tag、作者...'
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('BaseRenderTest', () => {
    it('Should正确RenderSearchInput框', () => {
      render(<SearchFilter {...defaultProps} />);
      
      const searchInput = screen.getByPlaceholderText('Search文章、Tag、作者...');
      expect(searchInput).toBeInTheDocument();
      expect(searchInput).toHaveAttribute('aria-label', 'Search');
    });

    it('ShouldDisplaySearch图标', () => {
      render(<SearchFilter {...defaultProps} />);
      
      const searchIcon = screen.getByRole('img', { name: 'search' });
      expect(searchIcon).toBeInTheDocument();
    });

    it('ShouldDisplay历史Button', () => {
      render(<SearchFilter {...defaultProps} />);
      
      const historyButton = screen.getByRole('button', { name: '查看Search历史' });
      expect(historyButton).toBeInTheDocument();
      expect(historyButton).toHaveAttribute('aria-label', '查看Search历史');
    });

    it('ShouldDisplay筛选Button', () => {
      render(<SearchFilter {...defaultProps} />);
      
      const filterButton = screen.getByRole('button', { name: 'Open筛选选项' });
      expect(filterButton).toBeInTheDocument();
      expect(filterButton).toHaveAttribute('aria-label', 'Open筛选选项');
    });

    it('ShouldDisplaySearch统计Information', () => {
      render(<SearchFilter {...defaultProps} />);
      
      expect(screen.getByText('共 10 项')).toBeInTheDocument();
      expect(screen.getByText('筛选出 10 项')).toBeInTheDocument();
      expect(screen.getByText('耗时 50ms')).toBeInTheDocument();
    });
  });

  describe('Search功能Test', () => {
    it('ShouldProcessSearchInput', async () => {
      const user = userEvent.setup();
      render(<SearchFilter {...defaultProps} />);
      
      const searchInput = screen.getByPlaceholderText('Search文章、Tag、作者...');
      await act(async () => {
        await user.type(searchInput, 'React');
      });
      
      expect(defaultProps.onSearch).toHaveBeenCalledWith('React');
    });

    it('ShouldDisplay清除ButtonWhen有SearchContent时', async () => {
      const user = userEvent.setup();
      render(<SearchFilter {...defaultProps} value="React" />);
      
      const clearButton = screen.getByRole('img', { name: 'close' });
      expect(clearButton).toBeInTheDocument();
    });

    it('Should清除SearchContent', async () => {
      const user = userEvent.setup();
      render(<SearchFilter {...defaultProps} value="React" />);
      
      const clearButton = screen.getByRole('img', { name: 'close' });
      await act(async () => {
        await user.click(clearButton);
      });
      
      expect(defaultProps.onSearch).toHaveBeenCalledWith('');
    });

    it('ShouldProcess空SearchValue', async () => {
      const user = userEvent.setup();
      render(<SearchFilter {...defaultProps} />);
      
      const searchInput = screen.getByPlaceholderText('Search文章、Tag、作者...');
      await act(async () => {
        await user.type(searchInput, '   ');
      });
      
      expect(defaultProps.onSearch).toHaveBeenCalledWith('   ');
    });
  });

  describe('历史记录功能Test', () => {
    it('ShouldDisplay历史记录下拉Menu', async () => {
      const user = userEvent.setup();
      render(<SearchFilter {...defaultProps} />);
      
      const historyButton = screen.getByRole('button', { name: '查看Search历史' });
      await act(async () => {
        await user.click(historyButton);
      });
      
      // 等待下拉MenuRender
      await waitFor(() => {
        expect(screen.getByText('ReactComponentDevelopment')).toBeInTheDocument();
      });
    });

    it('ShouldProcess历史记录Click', async () => {
      const user = userEvent.setup();
      render(<SearchFilter {...defaultProps} />);
      
      const historyButton = screen.getByRole('button', { name: '查看Search历史' });
      await act(async () => {
        await user.click(historyButton);
      });
      
      await waitFor(() => {
        const historyItem = screen.getByText('ReactComponentDevelopment');
        expect(historyItem).toBeInTheDocument();
      });
      
      const historyItem = screen.getByText('ReactComponentDevelopment');
      await act(async () => {
        await user.click(historyItem);
      });
      
      expect(defaultProps.onHistoryClick).toHaveBeenCalledWith(
        expect.objectContaining({
          text: 'ReactComponentDevelopment',
          type: 'recent'
        })
      );
    });

    it('ShouldProcess历史记录Delete', async () => {
      const user = userEvent.setup();
      render(<SearchFilter {...defaultProps} />);
      
      const historyButton = screen.getByRole('button', { name: '查看Search历史' });
      await act(async () => {
        await user.click(historyButton);
      });
      
      await waitFor(() => {
        expect(screen.getByText('ReactComponentDevelopment')).toBeInTheDocument();
      });
      
      // 找到DeleteButton并Click
      const deleteButtons = screen.getAllByLabelText('Delete历史');
      await act(async () => {
        await user.click(deleteButtons[0]);
      });
      
      expect(defaultProps.onHistoryDelete).toHaveBeenCalledWith(
        expect.objectContaining({
          text: 'ReactComponentDevelopment'
        })
      );
    });

    it('ShouldProcess清空历史记录', async () => {
      const user = userEvent.setup();
      render(<SearchFilter {...defaultProps} />);
      
      const historyButton = screen.getByRole('button', { name: '查看Search历史' });
      await act(async () => {
        await user.click(historyButton);
      });
      
      await waitFor(() => {
        expect(screen.getByText('清空历史')).toBeInTheDocument();
      });
      
      const clearHistoryButton = screen.getByText('清空历史');
      await act(async () => {
        await user.click(clearHistoryButton);
      });
      
      expect(defaultProps.onHistoryClear).toHaveBeenCalled();
    });

    it('ShouldDisplay更多历史选项When历史记录超过5条时', async () => {
      const user = userEvent.setup();
      render(<SearchFilter {...defaultProps} />);
      
      const historyButton = screen.getByRole('button', { name: '查看Search历史' });
      await act(async () => {
        await user.click(historyButton);
      });
      
      await waitFor(() => {
        expect(screen.getByText('更多历史')).toBeInTheDocument();
      });
    });
  });

  describe('筛选功能Test', () => {
    it('ShouldDisplay筛选下拉Menu', async () => {
      const user = userEvent.setup();
      render(<SearchFilter {...defaultProps} />);
      
      const filterButton = screen.getByRole('button', { name: 'Open筛选选项' });
      await act(async () => {
        await user.click(filterButton);
      });
      
      // 等待下拉MenuRender
      await waitFor(() => {
        expect(screen.getByText('Category')).toBeInTheDocument();
        expect(screen.getByText('Type')).toBeInTheDocument();
        expect(screen.getByText('Status')).toBeInTheDocument();
        expect(screen.getByText('作者')).toBeInTheDocument();
      });
    });

    it('ShouldProcess筛选Reset', async () => {
      const user = userEvent.setup();
      render(<SearchFilter {...defaultProps} />);
      
      const filterButton = screen.getByRole('button', { name: 'Open筛选选项' });
      await act(async () => {
        await user.click(filterButton);
      });
      
      await waitFor(() => {
        expect(screen.getByText('Reset筛选')).toBeInTheDocument();
      });
      
      const resetButton = screen.getByText('Reset筛选');
      await act(async () => {
        await user.click(resetButton);
      });
      
      expect(defaultProps.onFilterReset).toHaveBeenCalled();
    });
  });

  describe('Boundary情况Test', () => {
    it('ShouldProcess空的Search历史', () => {
      render(<SearchFilter {...defaultProps} searchHistory={[]} />);
      
      const historyButton = screen.queryByRole('button', { name: '查看Search历史' });
      expect(historyButton).not.toBeInTheDocument();
    });

    it('ShouldProcess空的筛选选项', () => {
      render(<SearchFilter {...defaultProps} filterOptions={[]} />);
      
      const filterButton = screen.queryByRole('button', { name: 'Open筛选选项' });
      expect(filterButton).not.toBeInTheDocument();
    });

    it('ShouldProcess空的Search统计', () => {
      render(<SearchFilter {...defaultProps} searchStats={undefined} />);
      
      expect(screen.queryByText('共 10 项')).not.toBeInTheDocument();
      expect(screen.queryByText('筛选出 10 项')).not.toBeInTheDocument();
      expect(screen.queryByText('耗时 50ms')).not.toBeInTheDocument();
    });

    it('ShouldProcess未Definition的CallbackFunction', async () => {
      const user = userEvent.setup();
      render(
        <SearchFilter
          onSearch={jest.fn()}
          searchHistory={mockSearchHistory}
          filterOptions={mockFilterOptions}
        />
      );
      
      // TestSearch
      const searchInput = screen.getByPlaceholderText('Search文章、Tag、作者...');
      await act(async () => {
        await user.type(searchInput, 'test');
      });
      
      // Test历史记录Click
      const historyButton = screen.getByRole('button', { name: '查看Search历史' });
      await act(async () => {
        await user.click(historyButton);
      });
      
      // Test筛选
      const filterButton = screen.getByRole('button', { name: 'Open筛选选项' });
      await act(async () => {
        await user.click(filterButton);
      });
      
      // 这些Operation不Should抛出Error
      expect(true).toBe(true);
    });
  });

  describe('可访问性Test', () => {
    it('SearchInput框Should有正确的ariaTag', () => {
      render(<SearchFilter {...defaultProps} />);
      
      const searchInput = screen.getByPlaceholderText('Search文章、Tag、作者...');
      expect(searchInput).toHaveAttribute('aria-label', 'Search');
    });

    it('ButtonShould有正确的ariaTag', () => {
      render(<SearchFilter {...defaultProps} />);
      
      const historyButton = screen.getByRole('button', { name: '查看Search历史' });
      const filterButton = screen.getByRole('button', { name: 'Open筛选选项' });
      
      expect(historyButton).toHaveAttribute('aria-label', '查看Search历史');
      expect(filterButton).toHaveAttribute('aria-label', 'Open筛选选项');
    });

    it('ShouldSupport键盘Navigation', async () => {
      const user = userEvent.setup();
      render(<SearchFilter {...defaultProps} />);
      
      const searchInput = screen.getByPlaceholderText('Search文章、Tag、作者...');
      await act(async () => {
        await user.tab();
      });
      expect(searchInput).toHaveFocus();
      
      const historyButton = screen.getByRole('button', { name: '查看Search历史' });
      await act(async () => {
        await user.tab();
      });
      expect(historyButton).toHaveFocus();
      
      const filterButton = screen.getByRole('button', { name: 'Open筛选选项' });
      await act(async () => {
        await user.tab();
      });
      expect(filterButton).toHaveFocus();
    });
  });

  describe('国际化Test', () => {
    it('Should正确Display中文占位符', () => {
      render(<SearchFilter {...defaultProps} />);
      expect(screen.getByPlaceholderText('Search文章、Tag、作者...')).toBeInTheDocument();
    });

    it('Should正确Display中文Button文本', () => {
      render(<SearchFilter {...defaultProps} />);
      expect(screen.getByText('历史')).toBeInTheDocument();
      expect(screen.getByText('筛选')).toBeInTheDocument();
    });

    it('Should正确Display中文统计Information', () => {
      render(<SearchFilter {...defaultProps} />);
      expect(screen.getByText('共 10 项')).toBeInTheDocument();
      expect(screen.getByText('筛选出 10 项')).toBeInTheDocument();
      expect(screen.getByText('耗时 50ms')).toBeInTheDocument();
    });
  });

  describe('ToolFunctionTest', () => {
    describe('searchArticles', () => {
      it('Should返回AllDataWhenSearchValue为空', () => {
        const result = mockUtils.searchArticles(mockArticles, '');
        expect(result).toEqual(mockArticles);
      });

      it('Should返回AllDataWhenSearchValue只有空格', () => {
        const result = mockUtils.searchArticles(mockArticles, '   ');
        expect(result).toEqual(mockArticles);
      });

      it('Should根据标题Search', () => {
        const result = mockUtils.searchArticles(mockArticles, 'React');
        expect(result).toHaveLength(1);
        expect(result[0].title).toContain('React');
      });

      it('Should根据ContentSearch', () => {
        const result = mockUtils.searchArticles(mockArticles, 'Component设计');
        expect(result).toHaveLength(1);
        expect(result[0].content).toContain('Component设计');
      });

      it('Should根据TagSearch', () => {
        const result = mockUtils.searchArticles(mockArticles, 'TypeScript');
        expect(result).toHaveLength(1);
        expect(result[0].tags).toContain('TypeScript');
      });

      it('Should根据作者Search', () => {
        const result = mockUtils.searchArticles(mockArticles, '张三');
        expect(result).toHaveLength(1);
        expect(result[0].author).toBe('张三');
      });

      it('Should不区分Size写', () => {
        const result = mockUtils.searchArticles(mockArticles, 'react');
        expect(result).toHaveLength(1);
        expect(result[0].title).toContain('React');
      });

      it('Should返回多个匹配Result', () => {
        const result = mockUtils.searchArticles(mockArticles, 'Frontend');
        expect(result.length).toBeGreaterThan(1);
        result.forEach(item => {
          expect(
            item.title.includes('Frontend') ||
            item.content.includes('Frontend') ||
            item.tags.some(tag => tag.includes('Frontend'))
          ).toBe(true);
        });
      });
    });

    describe('filterArticles', () => {
      it('Should返回AllDataWhen没有筛选条件', () => {
        const result = mockUtils.filterArticles(mockArticles, {});
        expect(result).toEqual(mockArticles);
      });

      it('Should根据Category筛选', () => {
        const result = mockUtils.filterArticles(mockArticles, { category: 'frontend' });
        expect(result).toHaveLength(3); // 3个Frontend相关文章
        result.forEach(item => {
          expect(item.category).toBe('frontend');
        });
      });

      it('Should根据Type筛选', () => {
        const result = mockUtils.filterArticles(mockArticles, { type: 'article' });
        expect(result.length).toBeGreaterThan(0);
        result.forEach(item => {
          expect(item.type).toBe('article');
        });
      });

      it('Should根据Status筛选', () => {
        const result = mockUtils.filterArticles(mockArticles, { status: 'published' });
        expect(result.length).toBeGreaterThan(0);
        result.forEach(item => {
          expect(item.status).toBe('published');
        });
      });

      it('Should根据作者筛选', () => {
        const result = mockUtils.filterArticles(mockArticles, { author: '张三' });
        expect(result).toHaveLength(1);
        expect(result[0].author).toBe('张三');
      });

      it('ShouldSupport多个筛选条件', () => {
        const result = mockUtils.filterArticles(mockArticles, {
          category: 'frontend',
          type: 'article'
        });
        expect(result.length).toBeGreaterThan(0);
        result.forEach(item => {
          expect(item.category).toBe('frontend');
          expect(item.type).toBe('article');
        });
      });

      it('Should忽略空Value筛选条件', () => {
        const result = mockUtils.filterArticles(mockArticles, {
          category: 'frontend',
          type: null,
          status: undefined
        });
        expect(result).toHaveLength(3);
        result.forEach(item => {
          expect(item.category).toBe('frontend');
        });
      });
    });

    describe('addSearchHistory', () => {
      it('ShouldAdd新的Search历史', () => {
        const history: MockHistoryItem[] = [];
        const result = mockUtils.addSearchHistory(history, '新Search');
        
        expect(result).toHaveLength(1);
        expect(result[0].text).toBe('新Search');
        expect(result[0].type).toBe('recent');
      });

      it('Should将重复的Search移到Top', () => {
        const history: MockHistoryItem[] = [
          { text: '旧Search', timestamp: Date.now() - 1000, type: 'recent' }
        ];
        const result = mockUtils.addSearchHistory(history, '旧Search');
        
        expect(result).toHaveLength(1);
        expect(result[0].text).toBe('旧Search');
        expect(result[0].timestamp).toBeGreaterThan(history[0].timestamp);
      });

      it('ShouldLimit历史记录Count为10条', () => {
        const history: MockHistoryItem[] = Array.from({ length: 10 }, (_, i) => ({
          text: `Search${i}`,
          timestamp: Date.now() - i * 1000,
          type: 'recent' as const
        }));
        
        const result = mockUtils.addSearchHistory(history, '新Search');
        
        expect(result).toHaveLength(10);
        expect(result[0].text).toBe('新Search');
      });

      it('Should忽略空Search文本', () => {
        const history: MockHistoryItem[] = [
          { text: '旧Search', timestamp: Date.now(), type: 'recent' }
        ];
        const result = mockUtils.addSearchHistory(history, '');
        
        expect(result).toEqual(history);
      });
    });

    describe('removeSearchHistory', () => {
      it('ShouldDelete指定的Search历史', () => {
        const history: MockHistoryItem[] = [
          { text: 'Search1', timestamp: Date.now(), type: 'recent' },
          { text: 'Search2', timestamp: Date.now(), type: 'recent' }
        ];
        
        const result = mockUtils.removeSearchHistory(history, 'Search1');
        
        expect(result).toHaveLength(1);
        expect(result[0].text).toBe('Search2');
      });

      it('ShouldProcess不存在的Search文本', () => {
        const history: MockHistoryItem[] = [
          { text: 'Search1', timestamp: Date.now(), type: 'recent' }
        ];
        
        const result = mockUtils.removeSearchHistory(history, '不存在的Search');
        
        expect(result).toEqual(history);
      });
    });

    describe('clearSearchHistory', () => {
      it('Should清空AllSearch历史', () => {
        const result = mockUtils.clearSearchHistory();
        expect(result).toEqual([]);
      });
    });

    describe('generateSearchStats', () => {
      it('Should生成正确的Search统计', () => {
        const stats = mockUtils.generateSearchStats(100, 50);
        
        expect(stats.total).toBe(100);
        expect(stats.filtered).toBe(50);
        expect(stats.time).toBeGreaterThanOrEqual(50);
        expect(stats.time).toBeLessThanOrEqual(150);
      });
    });
  });
}); 