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
import { useTranslation } from 'react-i18next';

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
  const { t } = useTranslation();
  // 模拟数据
  const analyticsData: AnalyticsData = {
    totalDocuments: 156,
    totalQuestions: 89,
    totalViews: 2847,
    totalLikes: 423,
    activeUsers: 45,
    avgResponseTime: 2.3,
    growthRate: 12.5,
    topCategories: [
      { name: t('pages.knowledge.analytics.categoryNames.technical'), count: 67, percentage: 43 },
      { name: t('pages.knowledge.analytics.categoryNames.product'), count: 45, percentage: 29 },
      { name: t('pages.knowledge.analytics.categoryNames.management'), count: 32, percentage: 21 },
      { name: t('pages.knowledge.analytics.categoryNames.other'), count: 12, percentage: 7 },
    ],
    topDocuments: [
      { title: t('pages.knowledge.analytics.documents.quickStart'), views: 234, likes: 45, category: t('pages.knowledge.analytics.categoryNames.technical') },
      { title: t('pages.knowledge.analytics.documents.apiReference'), views: 189, likes: 32, category: t('pages.knowledge.analytics.categoryNames.technical') },
      { title: t('pages.knowledge.analytics.documents.userPermissions'), views: 156, likes: 28, category: t('pages.knowledge.analytics.categoryNames.management') },
      { title: t('pages.knowledge.analytics.documents.productIntro'), views: 134, likes: 25, category: t('pages.knowledge.analytics.categoryNames.product') },
      { title: t('pages.knowledge.analytics.documents.deploymentGuide'), views: 98, likes: 18, category: t('pages.knowledge.analytics.categoryNames.technical') },
    ],
    recentActivity: [
      { type: 'create', title: t('pages.knowledge.analytics.activities.createDbGuide'), user: t('pages.knowledge.analytics.authors.zhangSan'), time: t('pages.knowledge.analytics.timeAgo.hours2') },
      { type: 'edit', title: t('pages.knowledge.analytics.activities.editApiDocs'), user: t('pages.knowledge.analytics.authors.liSi'), time: t('pages.knowledge.analytics.timeAgo.hours4') },
      { type: 'question', title: t('pages.knowledge.analytics.activities.askSsl'), user: t('pages.knowledge.analytics.authors.wangWu'), time: t('pages.knowledge.analytics.timeAgo.hours6') },
      { type: 'answer', title: t('pages.knowledge.analytics.activities.answerLogin'), user: t('pages.knowledge.analytics.authors.zhaoLiu'), time: t('pages.knowledge.analytics.timeAgo.hours8') },
      { type: 'view', title: t('pages.knowledge.analytics.activities.viewPermissions'), user: t('pages.knowledge.analytics.authors.qianQi'), time: t('pages.knowledge.analytics.timeAgo.hours10') },
    ],
  };

  // 热门文档表格列
  const topDocumentsColumns: ColumnsType<AnalyticsData['topDocuments'][0]> = [
    {
      title: t('pages.knowledge.analytics.documentTitle'),
      dataIndex: 'title',
      key: 'title',
      render: (text) => (
        <div style={{ color: 'var(--primary-text)', cursor: 'pointer' }}>
          {text}
        </div>
      ),
    },
    {
      title: t('pages.knowledge.analytics.category'),
      dataIndex: 'category',
      key: 'category',
      width: 120,
    },
    {
      title: t('pages.knowledge.analytics.views'),
      dataIndex: 'views',
      key: 'views',
      width: 100,
      render: (value) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <EyeOutlined style={{ color: 'var(--text-secondary)' }} />
          {value}
        </div>
      ),
    },
    {
      title: t('pages.knowledge.analytics.likes'),
      dataIndex: 'likes',
      key: 'likes',
      width: 100,
      render: (value) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <LikeOutlined style={{ color: 'var(--text-secondary)' }} />
          {value}
        </div>
      ),
    },
  ];

  // 最近活动表格列
  const recentActivityColumns: ColumnsType<AnalyticsData['recentActivity'][0]> = [
    {
      title: t('pages.knowledge.analytics.activityType'),
      dataIndex: 'type',
      key: 'type',
      width: 100,
      render: (type) => {
        const typeConfig = {
          create: { text: t('pages.knowledge.analytics.activity.create'), color: 'success' },
          edit: { text: t('pages.knowledge.analytics.activity.edit'), color: 'processing' },
          question: { text: t('pages.knowledge.analytics.activity.question'), color: 'warning' },
          answer: { text: t('pages.knowledge.analytics.activity.answer'), color: 'default' },
          view: { text: t('pages.knowledge.analytics.activity.view'), color: 'default' },
        };
        const config = typeConfig[type as keyof typeof typeConfig];
        return <Tag color={config.color}>{config.text}</Tag>;
      },
    },
    {
      title: t('pages.knowledge.analytics.content'),
      dataIndex: 'title',
      key: 'title',
      render: (text) => (
        <div style={{ color: 'var(--primary-text)', cursor: 'pointer' }}>
          {text}
        </div>
      ),
    },
    {
      title: t('pages.knowledge.analytics.user'),
      dataIndex: 'user',
      key: 'user',
      width: 100,
    },
    {
      title: t('pages.knowledge.analytics.time'),
      dataIndex: 'time',
      key: 'time',
      width: 120,
    },
  ];

  return (
    <div>
      {/* 页面标题 */}
      <div style={{ marginBottom: 24 }}>
        <Title level={4} style={{ margin: 0 }}>{t('pages.knowledge.analytics.pageTitle')}</Title>
      </div>

      {/* 核心指标卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title={t('pages.knowledge.analytics.totalDocuments')}
              value={analyticsData.totalDocuments}
              prefix={<BookOutlined />}
              valueStyle={{ color: 'var(--primary-text)' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title={t('pages.knowledge.analytics.totalQuestions')}
              value={analyticsData.totalQuestions}
              prefix={<MessageOutlined />}
              valueStyle={{ color: 'var(--success-text)' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title={t('pages.knowledge.analytics.totalViews')}
              value={analyticsData.totalViews}
              prefix={<EyeOutlined />}
              valueStyle={{ color: 'var(--warning-text)' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title={t('pages.knowledge.analytics.totalLikes')}
              value={analyticsData.totalLikes}
              prefix={<LikeOutlined />}
              valueStyle={{ color: 'var(--error-text)' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 用户活跃度和响应时间 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title={t('pages.knowledge.analytics.activeUsers')}
              value={analyticsData.activeUsers}
              prefix={<UserOutlined />}
              valueStyle={{ color: 'var(--accent-text)' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title={t('pages.knowledge.analytics.averageResponseTime')}
              value={analyticsData.avgResponseTime}
              suffix={t('pages.schedule.calendar.minutes')}
              prefix={<ClockCircleOutlined />}
              valueStyle={{ color: 'var(--info-text)' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title={t('pages.knowledge.analytics.growthRate')}
              value={analyticsData.growthRate}
              suffix="%"
              prefix={<RiseOutlined />}
              valueStyle={{ color: 'var(--success-text)' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title={t('pages.knowledge.analytics.documentationCompleteness')}
              value={87}
              suffix="%"
              prefix={<FileTextOutlined />}
              valueStyle={{ color: 'var(--primary-text)' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 分类统计和热门文档 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} lg={12}>
          <Card title={t('pages.knowledge.analytics.categoryStatistics')} size="small">
            {analyticsData.topCategories.map((category, index) => (
              <div key={category.name + '-' + index} style={{ marginBottom: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                  <span>{category.name}</span>
                  <span>{t('pages.knowledge.analytics.articleCount', { count: category.count })}</span>
                </div>
                <Progress 
                  percent={category.percentage} 
                  size="small" 
                  strokeColor={index === 0 ? 'var(--primary-color)' : index === 1 ? 'var(--success-color)' : index === 2 ? 'var(--warning-color)' : 'var(--border-color)'}
                />
              </div>
            ))}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title={t('pages.knowledge.analytics.topDocuments')} size="small">
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
          <Card title={t('pages.knowledge.analytics.recentActivity')} size="small">
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
