// SearchFilter 组件测试用的模拟数据
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

// 模拟文章数据
export const mockArticles: MockArticle[] = [
  {
    id: 1,
    title: 'React组件开发最佳实践',
    category: 'frontend',
    type: 'article',
    status: 'published',
    author: '张三',
    tags: ['React', '组件', '前端'],
    content: '本文介绍了React组件开发的最佳实践，包括组件设计原则、性能优化技巧等。',
    createTime: '2024-01-15',
    updateTime: '2024-01-20'
  },
  {
    id: 2,
    title: 'TypeScript高级类型系统详解',
    category: 'frontend',
    type: 'tutorial',
    status: 'draft',
    author: '李四',
    tags: ['TypeScript', '类型系统', '前端'],
    content: '深入解析TypeScript的高级类型系统，包括泛型、条件类型、映射类型等。',
    createTime: '2024-01-10',
    updateTime: '2024-01-18'
  },
  {
    id: 3,
    title: 'Ant Design组件库使用指南',
    category: 'ui',
    type: 'guide',
    status: 'published',
    author: '王五',
    tags: ['Ant Design', 'UI组件', '设计系统'],
    content: '详细介绍Ant Design组件库的使用方法，包括基础组件和高级组件的使用技巧。',
    createTime: '2024-01-12',
    updateTime: '2024-01-19'
  },
  {
    id: 4,
    title: '前端性能优化实战',
    category: 'performance',
    type: 'article',
    status: 'published',
    author: '赵六',
    tags: ['性能优化', '前端', '最佳实践'],
    content: '从多个维度介绍前端性能优化的方法和技巧，包括代码分割、懒加载等。',
    createTime: '2024-01-08',
    updateTime: '2024-01-16'
  },
  {
    id: 5,
    title: 'CSS Grid布局完全指南',
    category: 'css',
    type: 'tutorial',
    status: 'published',
    author: '钱七',
    tags: ['CSS', 'Grid', '布局'],
    content: '全面介绍CSS Grid布局的使用方法，包括基础概念和高级技巧。',
    createTime: '2024-01-05',
    updateTime: '2024-01-14'
  },
  {
    id: 6,
    title: 'JavaScript异步编程模式',
    category: 'javascript',
    type: 'article',
    status: 'draft',
    author: '孙八',
    tags: ['JavaScript', '异步', 'Promise'],
    content: '深入探讨JavaScript异步编程的各种模式，包括回调、Promise、async/await等。',
    createTime: '2024-01-03',
    updateTime: '2024-01-12'
  },
  {
    id: 7,
    title: 'Vue.js组件通信机制',
    category: 'frontend',
    type: 'guide',
    status: 'published',
    author: '周九',
    tags: ['Vue.js', '组件', '通信'],
    content: '详细介绍Vue.js中组件间的通信机制，包括props、emit、vuex等。',
    createTime: '2024-01-01',
    updateTime: '2024-01-10'
  },
  {
    id: 8,
    title: 'Node.js后端开发实战',
    category: 'backend',
    type: 'tutorial',
    status: 'published',
    author: '吴十',
    tags: ['Node.js', '后端', 'API'],
    content: '从零开始学习Node.js后端开发，包括Express框架、数据库操作等。',
    createTime: '2023-12-28',
    updateTime: '2024-01-08'
  },
  {
    id: 9,
    title: '微前端架构设计与实现',
    category: 'architecture',
    type: 'article',
    status: 'draft',
    author: '郑十一',
    tags: ['微前端', '架构', '设计'],
    content: '探讨微前端架构的设计原则和实现方案，包括技术选型和最佳实践。',
    createTime: '2023-12-25',
    updateTime: '2024-01-05'
  },
  {
    id: 10,
    title: 'Web安全防护指南',
    category: 'security',
    type: 'guide',
    status: 'published',
    author: '王十二',
    tags: ['Web安全', '防护', '最佳实践'],
    content: '介绍Web应用安全防护的各种方法和技巧，包括XSS、CSRF等攻击的防护。',
    createTime: '2023-12-20',
    updateTime: '2024-01-02'
  }
];

// 模拟搜索历史数据
export const mockSearchHistory: MockHistoryItem[] = [
  { text: 'React组件开发', timestamp: Date.now() - 3600000, type: 'recent' },
  { text: 'TypeScript类型定义', timestamp: Date.now() - 7200000, type: 'popular' },
  { text: 'Ant Design使用指南', timestamp: Date.now() - 10800000, type: 'recent' },
  { text: '前端性能优化', timestamp: Date.now() - 14400000, type: 'popular' },
  { text: 'CSS Grid布局', timestamp: Date.now() - 18000000, type: 'recent' },
  { text: 'JavaScript异步编程', timestamp: Date.now() - 21600000, type: 'popular' },
  { text: 'Vue.js组件通信', timestamp: Date.now() - 25200000, type: 'recent' },
  { text: 'Node.js后端开发', timestamp: Date.now() - 28800000, type: 'recent' }
];

// 模拟筛选选项
export const mockFilterOptions: MockFilterOption[] = [
  {
    key: 'category',
    label: '分类',
    options: [
      { label: '前端开发', value: 'frontend' },
      { label: 'UI设计', value: 'ui' },
      { label: '性能优化', value: 'performance' },
      { label: 'CSS样式', value: 'css' },
      { label: 'JavaScript', value: 'javascript' },
      { label: '后端开发', value: 'backend' },
      { label: '架构设计', value: 'architecture' },
      { label: '安全防护', value: 'security' }
    ]
  },
  {
    key: 'type',
    label: '类型',
    options: [
      { label: '文章', value: 'article' },
      { label: '教程', value: 'tutorial' },
      { label: '指南', value: 'guide' }
    ]
  },
  {
    key: 'status',
    label: '状态',
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

// 模拟工具函数
export const mockUtils = {
  // 搜索文章
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

  // 添加搜索历史
  addSearchHistory: (history: MockHistoryItem[], searchText: string): MockHistoryItem[] => {
    if (!searchText.trim()) return history;
    
    return [
      { text: searchText, timestamp: Date.now(), type: 'recent' as const },
      ...history.filter(item => item.text !== searchText)
    ].slice(0, 10);
  },

  // 删除搜索历史
  removeSearchHistory: (history: MockHistoryItem[], searchText: string): MockHistoryItem[] => {
    return history.filter(item => item.text !== searchText);
  },

  // 清空搜索历史
  clearSearchHistory: (): MockHistoryItem[] => {
    return [];
  },

  // 生成搜索统计
  generateSearchStats: (total: number, filtered: number) => ({
    total,
    filtered,
    time: Math.floor(Math.random() * 100) + 50 // 模拟搜索时间
  })
}; 