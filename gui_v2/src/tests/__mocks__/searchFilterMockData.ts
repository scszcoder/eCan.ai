// SearchFilter ComponentTest用的模拟Data
export interface MockArticle {
  id: number;
  title: string;
  category: string;
  type: string;
  status: string;
  author: string;
  tags: string[];
  content: string;
  createTime: string;
  updateTime: string;
}

export interface MockHistoryItem {
  text: string;
  timestamp: number;
  type?: 'recent' | 'popular';
}

export interface MockFilterOption {
  key: string;
  label: string;
  options: { label: string; value: any }[];
}

// 模拟文章Data
export const mockArticles: MockArticle[] = [
  {
    id: 1,
    title: 'ReactComponentDevelopment最佳实践',
    category: 'frontend',
    type: 'article',
    status: 'published',
    author: '张三',
    tags: ['React', 'Component', 'Frontend'],
    content: '本文介绍了ReactComponentDevelopment的最佳实践，包括Component设计原则、PerformanceOptimize技巧等。',
    createTime: '2024-01-15',
    updateTime: '2024-01-20'
  },
  {
    id: 2,
    title: 'TypeScriptAdvancedTypeSystem详解',
    category: 'frontend',
    type: 'tutorial',
    status: 'draft',
    author: '李四',
    tags: ['TypeScript', 'TypeSystem', 'Frontend'],
    content: '深入ParseTypeScript的AdvancedTypeSystem，包括泛型、条件Type、MapType等。',
    createTime: '2024-01-10',
    updateTime: '2024-01-18'
  },
  {
    id: 3,
    title: 'Ant DesignComponent库使用指南',
    category: 'ui',
    type: 'guide',
    status: 'published',
    author: '王五',
    tags: ['Ant Design', 'UIComponent', '设计System'],
    content: 'Detailed介绍Ant DesignComponent库的使用Method，包括BaseComponent和AdvancedComponent的使用技巧。',
    createTime: '2024-01-12',
    updateTime: '2024-01-19'
  },
  {
    id: 4,
    title: 'FrontendPerformanceOptimize实战',
    category: 'performance',
    type: 'article',
    status: 'published',
    author: '赵六',
    tags: ['PerformanceOptimize', 'Frontend', '最佳实践'],
    content: '从多个维度介绍FrontendPerformanceOptimize的Method和技巧，包括Code分割、懒Load等。',
    createTime: '2024-01-08',
    updateTime: '2024-01-16'
  },
  {
    id: 5,
    title: 'CSS GridLayout完全指南',
    category: 'css',
    type: 'tutorial',
    status: 'published',
    author: '钱七',
    tags: ['CSS', 'Grid', 'Layout'],
    content: '全面介绍CSS GridLayout的使用Method，包括Base概念和Advanced技巧。',
    createTime: '2024-01-05',
    updateTime: '2024-01-14'
  },
  {
    id: 6,
    title: 'JavaScriptAsync编程模式',
    category: 'javascript',
    type: 'article',
    status: 'draft',
    author: '孙八',
    tags: ['JavaScript', 'Async', 'Promise'],
    content: '深入探讨JavaScriptAsync编程的各种模式，包括Callback、Promise、async/await等。',
    createTime: '2024-01-03',
    updateTime: '2024-01-12'
  },
  {
    id: 7,
    title: 'Vue.jsComponent通信机制',
    category: 'frontend',
    type: 'guide',
    status: 'published',
    author: '周九',
    tags: ['Vue.js', 'Component', '通信'],
    content: 'Detailed介绍Vue.js中Component间的通信机制，包括props、emit、vuex等。',
    createTime: '2024-01-01',
    updateTime: '2024-01-10'
  },
  {
    id: 8,
    title: 'Node.jsBackendDevelopment实战',
    category: 'backend',
    type: 'tutorial',
    status: 'published',
    author: '吴十',
    tags: ['Node.js', 'Backend', 'API'],
    content: '从零开始学习Node.jsBackendDevelopment，包括Express框架、Data库Operation等。',
    createTime: '2023-12-28',
    updateTime: '2024-01-08'
  },
  {
    id: 9,
    title: '微Frontend架构设计与Implementation',
    category: 'architecture',
    type: 'article',
    status: 'draft',
    author: '郑十一',
    tags: ['微Frontend', '架构', '设计'],
    content: '探讨微Frontend架构的设计原则和Implementation方案，包括技术选型和最佳实践。',
    createTime: '2023-12-25',
    updateTime: '2024-01-05'
  },
  {
    id: 10,
    title: 'WebSecurity防护指南',
    category: 'security',
    type: 'guide',
    status: 'published',
    author: '王十二',
    tags: ['WebSecurity', '防护', '最佳实践'],
    content: '介绍Web应用Security防护的各种Method和技巧，包括XSS、CSRF等攻击的防护。',
    createTime: '2023-12-20',
    updateTime: '2024-01-02'
  }
];

// 模拟Search历史Data
export const mockSearchHistory: MockHistoryItem[] = [
  { text: 'ReactComponentDevelopment', timestamp: Date.now() - 3600000, type: 'recent' },
  { text: 'TypeScriptTypeDefinition', timestamp: Date.now() - 7200000, type: 'popular' },
  { text: 'Ant Design使用指南', timestamp: Date.now() - 10800000, type: 'recent' },
  { text: 'FrontendPerformanceOptimize', timestamp: Date.now() - 14400000, type: 'popular' },
  { text: 'CSS GridLayout', timestamp: Date.now() - 18000000, type: 'recent' },
  { text: 'JavaScriptAsync编程', timestamp: Date.now() - 21600000, type: 'popular' },
  { text: 'Vue.jsComponent通信', timestamp: Date.now() - 25200000, type: 'recent' },
  { text: 'Node.jsBackendDevelopment', timestamp: Date.now() - 28800000, type: 'recent' }
];

// 模拟筛选选项
export const mockFilterOptions: MockFilterOption[] = [
  {
    key: 'category',
    label: 'Category',
    options: [
      { label: 'FrontendDevelopment', value: 'frontend' },
      { label: 'UI设计', value: 'ui' },
      { label: 'PerformanceOptimize', value: 'performance' },
      { label: 'CSS样式', value: 'css' },
      { label: 'JavaScript', value: 'javascript' },
      { label: 'BackendDevelopment', value: 'backend' },
      { label: '架构设计', value: 'architecture' },
      { label: 'Security防护', value: 'security' }
    ]
  },
  {
    key: 'type',
    label: 'Type',
    options: [
      { label: '文章', value: 'article' },
      { label: '教程', value: 'tutorial' },
      { label: '指南', value: 'guide' }
    ]
  },
  {
    key: 'status',
    label: 'Status',
    options: [
      { label: '已发布', value: 'published' },
      { label: '草稿', value: 'draft' }
    ]
  },
  {
    key: 'author',
    label: '作者',
    options: [
      { label: '张三', value: '张三' },
      { label: '李四', value: '李四' },
      { label: '王五', value: '王五' },
      { label: '赵六', value: '赵六' },
      { label: '钱七', value: '钱七' },
      { label: '孙八', value: '孙八' },
      { label: '周九', value: '周九' },
      { label: '吴十', value: '吴十' },
      { label: '郑十一', value: '郑十一' },
      { label: '王十二', value: '王十二' }
    ]
  }
];

// 模拟ToolFunction
export const mockUtils = {
  // Search文章
  searchArticles: (data: MockArticle[], searchValue: string): MockArticle[] => {
    if (!searchValue.trim()) {
      return data;
    }

    return data.filter(item => 
      item.title.toLowerCase().includes(searchValue.toLowerCase()) ||
      item.content.toLowerCase().includes(searchValue.toLowerCase()) ||
      item.tags.some(tag => tag.toLowerCase().includes(searchValue.toLowerCase())) ||
      item.author.toLowerCase().includes(searchValue.toLowerCase())
    );
  },

  // 筛选文章
  filterArticles: (data: MockArticle[], filters: Record<string, any>): MockArticle[] => {
    let results = [...data];
    
    Object.entries(filters).forEach(([key, value]) => {
      if (value) {
        results = results.filter(item => {
          const itemValue = (item as any)[key];
          return itemValue === value;
        });
      }
    });
    
    return results;
  },

  // AddSearch历史
  addSearchHistory: (history: MockHistoryItem[], searchText: string): MockHistoryItem[] => {
    if (!searchText.trim()) return history;
    
    return [
      { text: searchText, timestamp: Date.now(), type: 'recent' as const },
      ...history.filter(item => item.text !== searchText)
    ].slice(0, 10);
  },

  // DeleteSearch历史
  removeSearchHistory: (history: MockHistoryItem[], searchText: string): MockHistoryItem[] => {
    return history.filter(item => item.text !== searchText);
  },

  // 清空Search历史
  clearSearchHistory: (): MockHistoryItem[] => {
    return [];
  },

  // 生成Search统计
  generateSearchStats: (total: number, filtered: number) => ({
    total,
    filtered,
    time: Math.floor(Math.random() * 100) + 50 // 模拟SearchTime
  })
}; 