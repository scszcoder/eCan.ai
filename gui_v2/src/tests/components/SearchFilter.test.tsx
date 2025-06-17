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
        'search.placeholder': '搜索文章、标签、作者...',
        'search.clear': '清除',
        'search.history': '历史',
        'search.filters': '筛选',
        'search.deleteHistory': '删除历史',
        'search.clearHistory': '清空历史',
        'search.moreHistory': '更多历史',
        'search.resetFilters': '重置筛选',
        'search.selectFilter': `选择${params?.filter || ''}`,
        'search.totalResults': `共 ${params?.count || 0} 项`,
        'search.filteredResults': `筛选出 ${params?.count || 0} 项`,
        'search.searchTime': `耗时 ${params?.time || 0}ms`,
        'search.justNow': '刚刚',
        'search.minutesAgo': `${params?.count || 0} 分钟前`,
        'search.hoursAgo': `${params?.count || 0} 小时前`,
        'search.daysAgo': `${params?.count || 0} 天前`,
        'search.ariaSearch': '搜索',
        'search.ariaHistory': '查看搜索历史',
        'search.ariaFilter': '打开筛选选项',
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
    placeholder: '搜索文章、标签、作者...'
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('基础渲染测试', () => {
    it('应该正确渲染搜索输入框', () => {
      render(<SearchFilter {...defaultProps} />);
      
      const searchInput = screen.getByPlaceholderText('搜索文章、标签、作者...');
      expect(searchInput).toBeInTheDocument();
      expect(searchInput).toHaveAttribute('aria-label', '搜索');
    });

    it('应该显示搜索图标', () => {
      render(<SearchFilter {...defaultProps} />);
      
      const searchIcon = screen.getByRole('img', { name: 'search' });
      expect(searchIcon).toBeInTheDocument();
    });

    it('应该显示历史按钮', () => {
      render(<SearchFilter {...defaultProps} />);
      
      const historyButton = screen.getByRole('button', { name: '查看搜索历史' });
      expect(historyButton).toBeInTheDocument();
      expect(historyButton).toHaveAttribute('aria-label', '查看搜索历史');
    });

    it('应该显示筛选按钮', () => {
      render(<SearchFilter {...defaultProps} />);
      
      const filterButton = screen.getByRole('button', { name: '打开筛选选项' });
      expect(filterButton).toBeInTheDocument();
      expect(filterButton).toHaveAttribute('aria-label', '打开筛选选项');
    });

    it('应该显示搜索统计信息', () => {
      render(<SearchFilter {...defaultProps} />);
      
      expect(screen.getByText('共 10 项')).toBeInTheDocument();
      expect(screen.getByText('筛选出 10 项')).toBeInTheDocument();
      expect(screen.getByText('耗时 50ms')).toBeInTheDocument();
    });
  });

  describe('搜索功能测试', () => {
    it('应该处理搜索输入', async () => {
      const user = userEvent.setup();
      render(<SearchFilter {...defaultProps} />);
      
      const searchInput = screen.getByPlaceholderText('搜索文章、标签、作者...');
      await act(async () => {
        await user.type(searchInput, 'React');
      });
      
      expect(defaultProps.onSearch).toHaveBeenCalledWith('React');
    });

    it('应该显示清除按钮当有搜索内容时', async () => {
      const user = userEvent.setup();
      render(<SearchFilter {...defaultProps} value="React" />);
      
      const clearButton = screen.getByRole('img', { name: 'close' });
      expect(clearButton).toBeInTheDocument();
    });

    it('应该清除搜索内容', async () => {
      const user = userEvent.setup();
      render(<SearchFilter {...defaultProps} value="React" />);
      
      const clearButton = screen.getByRole('img', { name: 'close' });
      await act(async () => {
        await user.click(clearButton);
      });
      
      expect(defaultProps.onSearch).toHaveBeenCalledWith('');
    });

    it('应该处理空搜索值', async () => {
      const user = userEvent.setup();
      render(<SearchFilter {...defaultProps} />);
      
      const searchInput = screen.getByPlaceholderText('搜索文章、标签、作者...');
      await act(async () => {
        await user.type(searchInput, '   ');
      });
      
      expect(defaultProps.onSearch).toHaveBeenCalledWith('   ');
    });
  });

  describe('历史记录功能测试', () => {
    it('应该显示历史记录下拉菜单', async () => {
      const user = userEvent.setup();
      render(<SearchFilter {...defaultProps} />);
      
      const historyButton = screen.getByRole('button', { name: '查看搜索历史' });
      await act(async () => {
        await user.click(historyButton);
      });
      
      // 等待下拉菜单渲染
      await waitFor(() => {
        expect(screen.getByText('React组件开发')).toBeInTheDocument();
      });
    });

    it('应该处理历史记录点击', async () => {
      const user = userEvent.setup();
      render(<SearchFilter {...defaultProps} />);
      
      const historyButton = screen.getByRole('button', { name: '查看搜索历史' });
      await act(async () => {
        await user.click(historyButton);
      });
      
      await waitFor(() => {
        const historyItem = screen.getByText('React组件开发');
        expect(historyItem).toBeInTheDocument();
      });
      
      const historyItem = screen.getByText('React组件开发');
      await act(async () => {
        await user.click(historyItem);
      });
      
      expect(defaultProps.onHistoryClick).toHaveBeenCalledWith(
        expect.objectContaining({
          text: 'React组件开发',
          type: 'recent'
        })
      );
    });

    it('应该处理历史记录删除', async () => {
      const user = userEvent.setup();
      render(<SearchFilter {...defaultProps} />);
      
      const historyButton = screen.getByRole('button', { name: '查看搜索历史' });
      await act(async () => {
        await user.click(historyButton);
      });
      
      await waitFor(() => {
        expect(screen.getByText('React组件开发')).toBeInTheDocument();
      });
      
      // 找到删除按钮并点击
      const deleteButtons = screen.getAllByLabelText('删除历史');
      await act(async () => {
        await user.click(deleteButtons[0]);
      });
      
      expect(defaultProps.onHistoryDelete).toHaveBeenCalledWith(
        expect.objectContaining({
          text: 'React组件开发'
        })
      );
    });

    it('应该处理清空历史记录', async () => {
      const user = userEvent.setup();
      render(<SearchFilter {...defaultProps} />);
      
      const historyButton = screen.getByRole('button', { name: '查看搜索历史' });
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

    it('应该显示更多历史选项当历史记录超过5条时', async () => {
      const user = userEvent.setup();
      render(<SearchFilter {...defaultProps} />);
      
      const historyButton = screen.getByRole('button', { name: '查看搜索历史' });
      await act(async () => {
        await user.click(historyButton);
      });
      
      await waitFor(() => {
        expect(screen.getByText('更多历史')).toBeInTheDocument();
      });
    });
  });

  describe('筛选功能测试', () => {
    it('应该显示筛选下拉菜单', async () => {
      const user = userEvent.setup();
      render(<SearchFilter {...defaultProps} />);
      
      const filterButton = screen.getByRole('button', { name: '打开筛选选项' });
      await act(async () => {
        await user.click(filterButton);
      });
      
      // 等待下拉菜单渲染
      await waitFor(() => {
        expect(screen.getByText('分类')).toBeInTheDocument();
        expect(screen.getByText('类型')).toBeInTheDocument();
        expect(screen.getByText('状态')).toBeInTheDocument();
        expect(screen.getByText('作者')).toBeInTheDocument();
      });
    });

    it('应该处理筛选重置', async () => {
      const user = userEvent.setup();
      render(<SearchFilter {...defaultProps} />);
      
      const filterButton = screen.getByRole('button', { name: '打开筛选选项' });
      await act(async () => {
        await user.click(filterButton);
      });
      
      await waitFor(() => {
        expect(screen.getByText('重置筛选')).toBeInTheDocument();
      });
      
      const resetButton = screen.getByText('重置筛选');
      await act(async () => {
        await user.click(resetButton);
      });
      
      expect(defaultProps.onFilterReset).toHaveBeenCalled();
    });
  });

  describe('边界情况测试', () => {
    it('应该处理空的搜索历史', () => {
      render(<SearchFilter {...defaultProps} searchHistory={[]} />);
      
      const historyButton = screen.queryByRole('button', { name: '查看搜索历史' });
      expect(historyButton).not.toBeInTheDocument();
    });

    it('应该处理空的筛选选项', () => {
      render(<SearchFilter {...defaultProps} filterOptions={[]} />);
      
      const filterButton = screen.queryByRole('button', { name: '打开筛选选项' });
      expect(filterButton).not.toBeInTheDocument();
    });

    it('应该处理空的搜索统计', () => {
      render(<SearchFilter {...defaultProps} searchStats={undefined} />);
      
      expect(screen.queryByText('共 10 项')).not.toBeInTheDocument();
      expect(screen.queryByText('筛选出 10 项')).not.toBeInTheDocument();
      expect(screen.queryByText('耗时 50ms')).not.toBeInTheDocument();
    });

    it('应该处理未定义的回调函数', async () => {
      const user = userEvent.setup();
      render(
        <SearchFilter
          onSearch={jest.fn()}
          searchHistory={mockSearchHistory}
          filterOptions={mockFilterOptions}
        />
      );
      
      // 测试搜索
      const searchInput = screen.getByPlaceholderText('搜索文章、标签、作者...');
      await act(async () => {
        await user.type(searchInput, 'test');
      });
      
      // 测试历史记录点击
      const historyButton = screen.getByRole('button', { name: '查看搜索历史' });
      await act(async () => {
        await user.click(historyButton);
      });
      
      // 测试筛选
      const filterButton = screen.getByRole('button', { name: '打开筛选选项' });
      await act(async () => {
        await user.click(filterButton);
      });
      
      // 这些操作不应该抛出错误
      expect(true).toBe(true);
    });
  });

  describe('可访问性测试', () => {
    it('搜索输入框应该有正确的aria标签', () => {
      render(<SearchFilter {...defaultProps} />);
      
      const searchInput = screen.getByPlaceholderText('搜索文章、标签、作者...');
      expect(searchInput).toHaveAttribute('aria-label', '搜索');
    });

    it('按钮应该有正确的aria标签', () => {
      render(<SearchFilter {...defaultProps} />);
      
      const historyButton = screen.getByRole('button', { name: '查看搜索历史' });
      const filterButton = screen.getByRole('button', { name: '打开筛选选项' });
      
      expect(historyButton).toHaveAttribute('aria-label', '查看搜索历史');
      expect(filterButton).toHaveAttribute('aria-label', '打开筛选选项');
    });

    it('应该支持键盘导航', async () => {
      const user = userEvent.setup();
      render(<SearchFilter {...defaultProps} />);
      
      const searchInput = screen.getByPlaceholderText('搜索文章、标签、作者...');
      await act(async () => {
        await user.tab();
      });
      expect(searchInput).toHaveFocus();
      
      const historyButton = screen.getByRole('button', { name: '查看搜索历史' });
      await act(async () => {
        await user.tab();
      });
      expect(historyButton).toHaveFocus();
      
      const filterButton = screen.getByRole('button', { name: '打开筛选选项' });
      await act(async () => {
        await user.tab();
      });
      expect(filterButton).toHaveFocus();
    });
  });

  describe('国际化测试', () => {
    it('应该正确显示中文占位符', () => {
      render(<SearchFilter {...defaultProps} />);
      expect(screen.getByPlaceholderText('搜索文章、标签、作者...')).toBeInTheDocument();
    });

    it('应该正确显示中文按钮文本', () => {
      render(<SearchFilter {...defaultProps} />);
      expect(screen.getByText('历史')).toBeInTheDocument();
      expect(screen.getByText('筛选')).toBeInTheDocument();
    });

    it('应该正确显示中文统计信息', () => {
      render(<SearchFilter {...defaultProps} />);
      expect(screen.getByText('共 10 项')).toBeInTheDocument();
      expect(screen.getByText('筛选出 10 项')).toBeInTheDocument();
      expect(screen.getByText('耗时 50ms')).toBeInTheDocument();
    });
  });

  describe('工具函数测试', () => {
    describe('searchArticles', () => {
      it('应该返回所有数据当搜索值为空', () => {
        const result = mockUtils.searchArticles(mockArticles, '');
        expect(result).toEqual(mockArticles);
      });

      it('应该返回所有数据当搜索值只有空格', () => {
        const result = mockUtils.searchArticles(mockArticles, '   ');
        expect(result).toEqual(mockArticles);
      });

      it('应该根据标题搜索', () => {
        const result = mockUtils.searchArticles(mockArticles, 'React');
        expect(result).toHaveLength(1);
        expect(result[0].title).toContain('React');
      });

      it('应该根据内容搜索', () => {
        const result = mockUtils.searchArticles(mockArticles, '组件设计');
        expect(result).toHaveLength(1);
        expect(result[0].content).toContain('组件设计');
      });

      it('应该根据标签搜索', () => {
        const result = mockUtils.searchArticles(mockArticles, 'TypeScript');
        expect(result).toHaveLength(1);
        expect(result[0].tags).toContain('TypeScript');
      });

      it('应该根据作者搜索', () => {
        const result = mockUtils.searchArticles(mockArticles, '张三');
        expect(result).toHaveLength(1);
        expect(result[0].author).toBe('张三');
      });

      it('应该不区分大小写', () => {
        const result = mockUtils.searchArticles(mockArticles, 'react');
        expect(result).toHaveLength(1);
        expect(result[0].title).toContain('React');
      });

      it('应该返回多个匹配结果', () => {
        const result = mockUtils.searchArticles(mockArticles, '前端');
        expect(result.length).toBeGreaterThan(1);
        result.forEach(item => {
          expect(
            item.title.includes('前端') ||
            item.content.includes('前端') ||
            item.tags.some(tag => tag.includes('前端'))
          ).toBe(true);
        });
      });
    });

    describe('filterArticles', () => {
      it('应该返回所有数据当没有筛选条件', () => {
        const result = mockUtils.filterArticles(mockArticles, {});
        expect(result).toEqual(mockArticles);
      });

      it('应该根据分类筛选', () => {
        const result = mockUtils.filterArticles(mockArticles, { category: 'frontend' });
        expect(result).toHaveLength(3); // 3个前端相关文章
        result.forEach(item => {
          expect(item.category).toBe('frontend');
        });
      });

      it('应该根据类型筛选', () => {
        const result = mockUtils.filterArticles(mockArticles, { type: 'article' });
        expect(result.length).toBeGreaterThan(0);
        result.forEach(item => {
          expect(item.type).toBe('article');
        });
      });

      it('应该根据状态筛选', () => {
        const result = mockUtils.filterArticles(mockArticles, { status: 'published' });
        expect(result.length).toBeGreaterThan(0);
        result.forEach(item => {
          expect(item.status).toBe('published');
        });
      });

      it('应该根据作者筛选', () => {
        const result = mockUtils.filterArticles(mockArticles, { author: '张三' });
        expect(result).toHaveLength(1);
        expect(result[0].author).toBe('张三');
      });

      it('应该支持多个筛选条件', () => {
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

      it('应该忽略空值筛选条件', () => {
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
      it('应该添加新的搜索历史', () => {
        const history: MockHistoryItem[] = [];
        const result = mockUtils.addSearchHistory(history, '新搜索');
        
        expect(result).toHaveLength(1);
        expect(result[0].text).toBe('新搜索');
        expect(result[0].type).toBe('recent');
      });

      it('应该将重复的搜索移到顶部', () => {
        const history: MockHistoryItem[] = [
          { text: '旧搜索', timestamp: Date.now() - 1000, type: 'recent' }
        ];
        const result = mockUtils.addSearchHistory(history, '旧搜索');
        
        expect(result).toHaveLength(1);
        expect(result[0].text).toBe('旧搜索');
        expect(result[0].timestamp).toBeGreaterThan(history[0].timestamp);
      });

      it('应该限制历史记录数量为10条', () => {
        const history: MockHistoryItem[] = Array.from({ length: 10 }, (_, i) => ({
          text: `搜索${i}`,
          timestamp: Date.now() - i * 1000,
          type: 'recent' as const
        }));
        
        const result = mockUtils.addSearchHistory(history, '新搜索');
        
        expect(result).toHaveLength(10);
        expect(result[0].text).toBe('新搜索');
      });

      it('应该忽略空搜索文本', () => {
        const history: MockHistoryItem[] = [
          { text: '旧搜索', timestamp: Date.now(), type: 'recent' }
        ];
        const result = mockUtils.addSearchHistory(history, '');
        
        expect(result).toEqual(history);
      });
    });

    describe('removeSearchHistory', () => {
      it('应该删除指定的搜索历史', () => {
        const history: MockHistoryItem[] = [
          { text: '搜索1', timestamp: Date.now(), type: 'recent' },
          { text: '搜索2', timestamp: Date.now(), type: 'recent' }
        ];
        
        const result = mockUtils.removeSearchHistory(history, '搜索1');
        
        expect(result).toHaveLength(1);
        expect(result[0].text).toBe('搜索2');
      });

      it('应该处理不存在的搜索文本', () => {
        const history: MockHistoryItem[] = [
          { text: '搜索1', timestamp: Date.now(), type: 'recent' }
        ];
        
        const result = mockUtils.removeSearchHistory(history, '不存在的搜索');
        
        expect(result).toEqual(history);
      });
    });

    describe('clearSearchHistory', () => {
      it('应该清空所有搜索历史', () => {
        const result = mockUtils.clearSearchHistory();
        expect(result).toEqual([]);
      });
    });

    describe('generateSearchStats', () => {
      it('应该生成正确的搜索统计', () => {
        const stats = mockUtils.generateSearchStats(100, 50);
        
        expect(stats.total).toBe(100);
        expect(stats.filtered).toBe(50);
        expect(stats.time).toBeGreaterThanOrEqual(50);
        expect(stats.time).toBeLessThanOrEqual(150);
      });
    });
  });
}); 