import React from 'react';
import { 
  Card, 
  Row, 
  Col, 
  Statistic, 
  Typography, 
  Table,
  Progress,
  Tag,
  Space
} from 'antd';
import { 
  BookOutlined,
  MessageOutlined,
  EyeOutlined,
  LikeOutlined,
  UserOutlined,
  ClockCircleOutlined,
  RiseOutlined,
  FileTextOutlined
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';

const { Title } = Typography;

interface AnalyticsData {
  totalDocuments: number;
  totalQuestions: number;
  totalViews: number;
  totalLikes: number;
  activeUsers: number;
  avgResponseTime: number;
  growthRate: number;
  topCategories: Array<{
    name: string;
    count: number;
    percentage: number;
  }>;
  topDocuments: Array<{
    title: string;
    views: number;
    likes: number;
    category: string;
  }>;
  recentActivity: Array<{
    type: string;
    title: string;
    user: string;
    time: string;
  }>;
}

const Analytics: React.FC = () => {
  // 模拟Data
  const analyticsData: AnalyticsData = {
    totalDocuments: 156,
    totalQuestions: 89,
    totalViews: 2847,
    totalLikes: 423,
    activeUsers: 45,
    avgResponseTime: 2.3,
    growthRate: 12.5,
    topCategories: [
      { name: '技术Documentation', count: 67, percentage: 43 },
      { name: '产品Documentation', count: 45, percentage: 29 },
      { name: '管理Documentation', count: 32, percentage: 21 },
      { name: '其他', count: 12, percentage: 7 },
    ],
    topDocuments: [
      { title: 'Fast开始指南', views: 234, likes: 45, category: '技术Documentation' },
      { title: 'API 参考Documentation', views: 189, likes: 32, category: '技术Documentation' },
      { title: 'UserPermission管理', views: 156, likes: 28, category: '管理Documentation' },
      { title: '产品功能介绍', views: 134, likes: 25, category: '产品Documentation' },
      { title: 'System部署指南', views: 98, likes: 18, category: '技术Documentation' },
    ],
    recentActivity: [
      { type: 'create', title: '新增Documentation：Data库Optimize指南', user: '张三', time: '2小时前' },
      { type: 'edit', title: 'UpdateDocumentation：APIInterface说明', user: '李四', time: '4小时前' },
      { type: 'question', title: '提问：如何ConfigurationSSL证书？', user: '王五', time: '6小时前' },
      { type: 'answer', title: '回答：SystemLogin问题解决方案', user: '赵六', time: '8小时前' },
      { type: 'view', title: '查看Documentation：UserPermission管理', user: '钱七', time: '10小时前' },
    ],
  };

  // 热门DocumentationTable列
  const topDocumentsColumns: ColumnsType<AnalyticsData['topDocuments'][0]> = [
    {
      title: 'Documentation标题',
      dataIndex: 'title',
      key: 'title',
      render: (text) => (
        <div style={{ color: '#1890ff', cursor: 'pointer' }}>
          {text}
        </div>
      ),
    },
    {
      title: 'Category',
      dataIndex: 'category',
      key: 'category',
      width: 120,
    },
    {
      title: '浏览量',
      dataIndex: 'views',
      key: 'views',
      width: 100,
      render: (value) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <EyeOutlined style={{ color: '#666' }} />
          {value}
        </div>
      ),
    },
    {
      title: '点赞数',
      dataIndex: 'likes',
      key: 'likes',
      width: 100,
      render: (value) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <LikeOutlined style={{ color: '#666' }} />
          {value}
        </div>
      ),
    },
  ];

  // 最近活动Table列
  const recentActivityColumns: ColumnsType<AnalyticsData['recentActivity'][0]> = [
    {
      title: '活动Type',
      dataIndex: 'type',
      key: 'type',
      width: 100,
      render: (type) => {
        const typeConfig = {
          create: { text: '新增', color: 'success' },
          edit: { text: 'Edit', color: 'processing' },
          question: { text: '提问', color: 'warning' },
          answer: { text: '回答', color: 'default' },
          view: { text: '查看', color: 'default' },
        };
        const config = typeConfig[type as keyof typeof typeConfig];
        return <Tag color={config.color}>{config.text}</Tag>;
      },
    },
    {
      title: 'Content',
      dataIndex: 'title',
      key: 'title',
      render: (text) => (
        <div style={{ color: '#1890ff', cursor: 'pointer' }}>
          {text}
        </div>
      ),
    },
    {
      title: 'User',
      dataIndex: 'user',
      key: 'user',
      width: 100,
    },
    {
      title: 'Time',
      dataIndex: 'time',
      key: 'time',
      width: 120,
    },
  ];

  return (
    <div>
      {/* Page标题 */}
      <div style={{ marginBottom: 24 }}>
        <Title level={4} style={{ margin: 0 }}>统计分析</Title>
      </div>

      {/* Core指标卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="总Documentation数"
              value={analyticsData.totalDocuments}
              prefix={<BookOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="总问答数"
              value={analyticsData.totalQuestions}
              prefix={<MessageOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="总浏览量"
              value={analyticsData.totalViews}
              prefix={<EyeOutlined />}
              valueStyle={{ color: '#faad14' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="总点赞数"
              value={analyticsData.totalLikes}
              prefix={<LikeOutlined />}
              valueStyle={{ color: '#f5222d' }}
            />
          </Card>
        </Col>
      </Row>

      {/* User活跃度和ResponseTime */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="活跃User"
              value={analyticsData.activeUsers}
              prefix={<UserOutlined />}
              valueStyle={{ color: '#722ed1' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="AverageResponseTime"
              value={analyticsData.avgResponseTime}
              suffix="分钟"
              prefix={<ClockCircleOutlined />}
              valueStyle={{ color: '#13c2c2' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="增长率"
              value={analyticsData.growthRate}
              suffix="%"
              prefix={<RiseOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="Documentation完整度"
              value={87}
              suffix="%"
              prefix={<FileTextOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
      </Row>

      {/* Category统计和热门Documentation */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} lg={12}>
          <Card title="Category统计" size="small">
            {analyticsData.topCategories.map((category, index) => (
              <div key={category.name + '-' + index} style={{ marginBottom: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                  <span>{category.name}</span>
                  <span>{category.count} 篇</span>
                </div>
                <Progress 
                  percent={category.percentage} 
                  size="small" 
                  strokeColor={index === 0 ? '#1890ff' : index === 1 ? '#52c41a' : index === 2 ? '#faad14' : '#d9d9d9'}
                />
              </div>
            ))}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="热门Documentation" size="small">
            <Table
              columns={topDocumentsColumns}
              dataSource={analyticsData.topDocuments}
              rowKey={(record) => record.title + '-' + record.category}
              pagination={false}
              size="small"
            />
          </Card>
        </Col>
      </Row>

      {/* 最近活动 */}
      <Row gutter={[16, 16]}>
        <Col span={24}>
          <Card title="最近活动" size="small">
            <Table
              columns={recentActivityColumns}
              dataSource={analyticsData.recentActivity}
              rowKey={(record) => record.type + '-' + record.title + '-' + record.user + '-' + record.time}
              pagination={false}
              size="small"
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default Analytics; 