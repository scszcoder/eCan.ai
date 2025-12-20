import React, { useState, useEffect } from 'react';
import { 
  Modal, 
  Form, 
  Input, 
  Select, 
  DatePicker, 
  Button, 
  Space, 
  Tag, 
  Card,
  Typography,
  Divider,
  Checkbox,
  Slider,
  message
} from 'antd';
import { 
  SearchOutlined,
  FilterOutlined,
  ClearOutlined,
  SaveOutlined,
  BookOutlined,
  UserOutlined,
  CalendarOutlined,
  TagOutlined
} from '@ant-design/icons';
import type { RangePickerProps } from 'antd/es/date-picker';

const { Option } = Select;
const { RangePicker } = DatePicker;
const { TextArea } = Input;
const { Title, Text } = Typography;

interface SearchCriteria {
  keyword: string;
  category: string[];
  tags: string[];
  author: string[];
  dateRange: [string, string] | null;
  contentType: string[];
  status: string[];
  minLength: number;
  maxLength: number;
}

interface SearchResult {
  id: number;
  title: string;
  content: string;
  category: string;
  tags: string[];
  author: string;
  createdAt: string;
  updatedAt: string;
  type: 'document' | 'qa';
  status?: string;
  relevance: number;
}

interface AdvancedSearchProps {
  visible: boolean;
  onClose: () => void;
  onSearch: (results: SearchResult[]) => void;
  dataSource: any[];
}

const AdvancedSearch: React.FC<AdvancedSearchProps> = ({
  visible,
  onClose,
  onSearch,
  dataSource
}) => {
  const [form] = Form.useForm();
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [savedSearches, setSavedSearches] = useState<Array<{name: string, criteria: SearchCriteria}>>([]);

  // GetAllAvailable的Category、Tag、作者等
  const categories = Array.from(new Set(dataSource.map(item => item.category))).filter(Boolean);
  const tags = Array.from(new Set(dataSource.flatMap(item => item.tags || []))).filter(Boolean);
  const authors = Array.from(new Set(dataSource.map(item => item.author || item.asker))).filter(Boolean);

  // ExecuteSearch
  const performSearch = async (criteria: SearchCriteria) => {
    setIsSearching(true);
    
    try {
      // 模拟SearchDelay
      await new Promise(resolve => setTimeout(resolve, 500));
      
      let results = [...dataSource];

      // 关键词Search
      if (criteria.keyword) {
        const keyword = criteria.keyword.toLowerCase();
        results = results.filter(item => 
          item.title?.toLowerCase().includes(keyword) ||
          item.content?.toLowerCase().includes(keyword) ||
          item.question?.toLowerCase().includes(keyword) ||
          item.answer?.toLowerCase().includes(keyword)
        );
      }

      // Category筛选
      if (criteria.category && criteria.category.length > 0) {
        results = results.filter(item => 
          criteria.category.includes(item.category)
        );
      }

      // Tag筛选
      if (criteria.tags && criteria.tags.length > 0) {
        results = results.filter(item => 
          item.tags && criteria.tags.some(tag => item.tags.includes(tag))
        );
      }

      // 作者筛选
      if (criteria.author && criteria.author.length > 0) {
        results = results.filter(item => 
          criteria.author.includes(item.author || item.asker)
        );
      }

      // DateRange筛选
      if (criteria.dateRange) {
        const [startDate, endDate] = criteria.dateRange;
        results = results.filter(item => {
          const itemDate = new Date(item.createdAt);
          const start = startDate ? new Date(startDate) : null;
          const end = endDate ? new Date(endDate) : null;
          
          if (start && end) {
            return itemDate >= start && itemDate <= end;
          } else if (start) {
            return itemDate >= start;
          } else if (end) {
            return itemDate <= end;
          }
          return true;
        });
      }

      // ContentType筛选
      if (criteria.contentType && criteria.contentType.length > 0) {
        results = results.filter(item => {
          if (criteria.contentType.includes('document')) {
            return item.title && item.content;
          }
          if (criteria.contentType.includes('qa')) {
            return item.question && item.answer;
          }
          return true;
        });
      }

      // Status筛选
      if (criteria.status && criteria.status.length > 0) {
        results = results.filter(item => 
          item.status && criteria.status.includes(item.status)
        );
      }

      // ContentLength筛选
      if (criteria.minLength > 0) {
        results = results.filter(item => {
          const content = item.content || item.answer || '';
          return content.length >= criteria.minLength;
        });
      }

      if (criteria.maxLength < 10000) {
        results = results.filter(item => {
          const content = item.content || item.answer || '';
          return content.length <= criteria.maxLength;
        });
      }

      // 计算相关性分数
      const scoredResults: SearchResult[] = results.map(item => ({
        id: item.id,
        title: item.title || item.question,
        content: item.content || item.answer,
        category: item.category,
        tags: item.tags || [],
        author: item.author || item.asker,
        createdAt: item.createdAt,
        updatedAt: item.updatedAt,
        type: item.question ? 'qa' : 'document',
        status: item.status,
        relevance: calculateRelevance(item, criteria),
      }));

      // 按相关性Sort
      scoredResults.sort((a, b) => b.relevance - a.relevance);

      setSearchResults(scoredResults);
      onSearch(scoredResults);
      message.success(`找到 ${scoredResults.length} 个Result`);
    } catch (error) {
      message.error('SearchFailed');
    } finally {
      setIsSearching(false);
    }
  };

  // 计算相关性分数
  const calculateRelevance = (item: any, criteria: SearchCriteria): number => {
    let score = 0;
    
    // 关键词匹配
    if (criteria.keyword) {
      const keyword = criteria.keyword.toLowerCase();
      if (item.title?.toLowerCase().includes(keyword)) score += 10;
      if (item.content?.toLowerCase().includes(keyword)) score += 5;
      if (item.question?.toLowerCase().includes(keyword)) score += 8;
      if (item.answer?.toLowerCase().includes(keyword)) score += 3;
    }

    // Tag匹配
    if (criteria.tags && item.tags) {
      const matchedTags = criteria.tags.filter(tag => item.tags.includes(tag));
      score += matchedTags.length * 2;
    }

    // Time权重（越新分数越高）
    const daysSinceCreation = (Date.now() - new Date(item.createdAt).getTime()) / (1000 * 60 * 60 * 24);
    score += Math.max(0, 10 - daysSinceCreation / 30);

    return score;
  };

  // ProcessSearch
  const handleSearch = async () => {
    try {
      const values = await form.validateFields();
      await performSearch(values);
    } catch (error) {
      console.error('Search validation failed:', error);
    }
  };

  // 清空Search条件
  const handleClear = () => {
    form.resetFields();
    setSearchResults([]);
  };

  // SaveSearch条件
  const handleSaveSearch = async () => {
    try {
      const values = await form.validateFields();
      const searchName = `Search_${new Date().toLocaleString()}`;
      const newSavedSearch = { name: searchName, criteria: values };
      setSavedSearches(prev => [...prev, newSavedSearch]);
      message.success('Search条件已Save');
    } catch (error) {
      message.error('SaveFailed');
    }
  };

  // LoadSave的Search
  const handleLoadSearch = (savedSearch: {name: string, criteria: SearchCriteria}) => {
    form.setFieldsValue(savedSearch.criteria);
    performSearch(savedSearch.criteria);
  };

  // Disabled过去的Date
  const disabledDate: RangePickerProps['disabledDate'] = (current) => {
    return current && current > new Date();
  };

  return (
    <Modal
      title="AdvancedSearch"
      open={visible}
      onCancel={onClose}
      width={1000}
      footer={null}
    >
      <div style={{ display: 'flex', gap: 16 }}>
        {/* Search条件面板 */}
        <div style={{ width: '40%' }}>
          <Form
            form={form}
            layout="vertical"
            initialValues={{
              keyword: '',
              category: [],
              tags: [],
              author: [],
              dateRange: null,
              contentType: ['document', 'qa'],
              status: [],
              minLength: 0,
              maxLength: 10000,
            }}
          >
            {/* 关键词Search */}
            <Form.Item name="keyword" label="关键词">
              <Input 
                placeholder="Search标题、Content、问题或答案..."
                prefix={<SearchOutlined />}
              />
            </Form.Item>

            {/* Category筛选 */}
            <Form.Item name="category" label="Category">
              <Select
                mode="multiple"
                placeholder="SelectCategory"
                allowClear
                options={categories.map(cat => ({ label: cat, value: cat }))}
              />
            </Form.Item>

            {/* Tag筛选 */}
            <Form.Item name="tags" label="Tag">
              <Select
                mode="multiple"
                placeholder="SelectTag"
                allowClear
                options={tags.map(tag => ({ label: tag, value: tag }))}
              />
            </Form.Item>

            {/* 作者筛选 */}
            <Form.Item name="author" label="作者">
              <Select
                mode="multiple"
                placeholder="Select作者"
                allowClear
                options={authors.map(author => ({ label: author, value: author }))}
              />
            </Form.Item>

            {/* DateRange */}
            <Form.Item name="dateRange" label="CreateTime">
              <RangePicker 
                style={{ width: '100%' }}
                disabledDate={disabledDate}
              />
            </Form.Item>

            {/* ContentType */}
            <Form.Item name="contentType" label="ContentType">
              <Checkbox.Group>
                <Space direction="vertical">
                  <Checkbox value="document">Documentation</Checkbox>
                  <Checkbox value="qa">问答</Checkbox>
                </Space>
              </Checkbox.Group>
            </Form.Item>

            {/* Status筛选 */}
            <Form.Item name="status" label="Status">
              <Select
                mode="multiple"
                placeholder="SelectStatus"
                allowClear
                options={[
                  { label: '已发布', value: 'published' },
                  { label: '草稿', value: 'draft' },
                  { label: '待审核', value: 'pending' },
                  { label: '已审核', value: 'approved' },
                ]}
              />
            </Form.Item>

            {/* ContentLength */}
            <Form.Item label="ContentLength">
              <div style={{ padding: '0 16px' }}>
                <Slider
                  range
                  min={0}
                  max={10000}
                  step={100}
                  marks={{
                    0: '0',
                    2500: '2.5K',
                    5000: '5K',
                    7500: '7.5K',
                    10000: '10K+'
                  }}
                />
              </div>
            </Form.Item>

            {/* OperationButton */}
            <Form.Item>
              <Space>
                <Button 
                  type="primary" 
                  icon={<SearchOutlined />}
                  onClick={handleSearch}
                  loading={isSearching}
                >
                  Search
                </Button>
                <Button 
                  icon={<ClearOutlined />}
                  onClick={handleClear}
                >
                  清空
                </Button>
                <Button 
                  icon={<SaveOutlined />}
                  onClick={handleSaveSearch}
                >
                  Save
                </Button>
              </Space>
            </Form.Item>
          </Form>

          {/* Save的Search */}
          {savedSearches.length > 0 && (
            <Card size="small" title="Save的Search">
              {savedSearches.map((savedSearch, index) => (
                <div key={index} style={{ marginBottom: 8 }}>
                  <Button 
                    type="link" 
                    size="small"
                    onClick={() => handleLoadSearch(savedSearch)}
                  >
                    {savedSearch.name}
                  </Button>
                </div>
              ))}
            </Card>
          )}
        </div>

        {/* SearchResult面板 */}
        <div style={{ flex: 1 }}>
          <div style={{ marginBottom: 16 }}>
            <Title level={5}>
              SearchResult ({searchResults.length})
            </Title>
          </div>

          <div style={{ maxHeight: 600, overflowX: 'hidden', overflowY: 'auto' }}>
            {searchResults.map((result) => (
              <Card 
                key={result.id} 
                size="small" 
                style={{ marginBottom: 12 }}
                hoverable
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ marginBottom: 8 }}>
                      <Text strong style={{ color: '#1890ff', cursor: 'pointer' }}>
                        {result.title}
                      </Text>
                      <Tag 
                        color={result.type === 'document' ? 'blue' : 'green'}
                        style={{ marginLeft: 8 }}
                      >
                        {result.type === 'document' ? 'Documentation' : '问答'}
                      </Tag>
                      <Tag color="orange" style={{ marginLeft: 4 }}>
                        相关性: {result.relevance}
                      </Tag>
                    </div>

                    <div style={{ marginBottom: 8, fontSize: 12, color: '#666' }}>
                      {result.content.substring(0, 150)}...
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: 16, fontSize: 12, color: '#666' }}>
                      <span>
                        <UserOutlined /> {result.author}
                      </span>
                      <span>
                        <CalendarOutlined /> {result.createdAt}
                      </span>
                      <span>
                        <TagOutlined /> {result.category}
                      </span>
                    </div>

                    {result.tags.length > 0 && (
                      <div style={{ marginTop: 8 }}>
                        {result.tags.map(tag => (
                          <Tag key={tag} size="small">{tag}</Tag>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </Card>
            ))}

            {searchResults.length === 0 && !isSearching && (
              <div style={{ textAlign: 'center', padding: 40, color: '#666' }}>
                <BookOutlined style={{ fontSize: 48, marginBottom: 16 }} />
                <div>暂无SearchResult</div>
                <div style={{ fontSize: 12 }}>尝试调整Search条件</div>
              </div>
            )}
          </div>
        </div>
      </div>
    </Modal>
  );
};

export default AdvancedSearch; 