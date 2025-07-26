import React, { useState, useEffect } from 'react';
import { Layout, Menu, Breadcrumb, Input, Avatar, Dropdown, Button, Space } from 'antd';
import {
  BookOutlined,
  MessageOutlined,
  QuestionCircleOutlined,
  FolderOutlined,
  BarChartOutlined,
  SettingOutlined,
  SearchOutlined,
  BellOutlined,
  UserOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined
} from '@ant-design/icons';
import KnowledgeBase from './KnowledgeBase';
import QAPlatform from './QAPlatform';
import ChatInterface from './ChatInterface';
import CategoryManagement from './CategoryManagement';
import Analytics from './Analytics';
import Settings from './Settings';
import { initializeDefaultData } from './services/storage';

const { Sider, Content } = Layout;
const { Search } = Input;

// 菜单配置
const menuItems = [
  {
    key: 'knowledge-base',
    icon: <BookOutlined />,
    label: '知识库管理',
  },
  {
    key: 'chat',
    icon: <MessageOutlined />,
    label: '智能问答',
  },
  {
    key: 'qa-management',
    icon: <QuestionCircleOutlined />,
    label: '问答管理',
  },
  {
    key: 'categories',
    icon: <FolderOutlined />,
    label: '分类管理',
  },
  {
    key: 'analytics',
    icon: <BarChartOutlined />,
    label: '统计分析',
  },
  {
    key: 'settings',
    icon: <SettingOutlined />,
    label: '设置',
  },
];

// 页面标题映射
const pageTitles = {
  'knowledge-base': '知识库管理',
  'chat': '智能问答',
  'qa-management': '问答管理',
  'categories': '分类管理',
  'analytics': '统计分析',
  'settings': '设置',
};

const KnowledgePlatform: React.FC = () => {
  const [selectedKey, setSelectedKey] = useState('chat');
  const [collapsed, setCollapsed] = useState(false);

  // 初始化默认数据
  useEffect(() => {
    initializeDefaultData();
  }, []);

  // 渲染主内容
  const renderContent = () => {
    switch (selectedKey) {
      case 'knowledge-base':
        return <KnowledgeBase />;
      case 'chat':
        return <ChatInterface />;
      case 'qa-management':
        return <QAPlatform />;
      case 'categories':
        return <CategoryManagement />;
      case 'analytics':
        return <Analytics />;
      case 'settings':
        return <Settings />;
      default:
        return <ChatInterface />;
    }
  };

  // 生成面包屑
  const generateBreadcrumb = () => {
    return [
      { title: '知识库平台' },
      { title: pageTitles[selectedKey as keyof typeof pageTitles] || '智能问答' },
    ];
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      {/* 左侧导航 */}
      <Sider 
        width={200} 
        collapsed={collapsed}
        style={{ 
          background: '#fff',
          borderRight: '1px solid #f0f0f0'
        }}
      >
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          style={{ 
            height: '100%', 
            borderRight: 0,
            paddingTop: 16
          }}
          items={menuItems}
          onClick={({ key }) => setSelectedKey(key)}
        />
      </Sider>

      {/* 主内容区 */}
      <Layout style={{ padding: '0 24px 24px' }}>
        {/* 面包屑导航 */}
        <div style={{ padding: '16px 0' }}>
          <Breadcrumb items={generateBreadcrumb()} />
        </div>

        {/* 内容区域 */}
        <Content style={{ 
          background: '#fff', 
          padding: 24,
          borderRadius: 8,
          minHeight: 280,
          boxShadow: '0 1px 2px rgba(0, 0, 0, 0.03)'
        }}>
          {renderContent()}
        </Content>
      </Layout>
    </Layout>
  );
};

export default KnowledgePlatform; 