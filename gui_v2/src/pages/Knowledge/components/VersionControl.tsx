import React, { useState } from 'react';
import { 
  Modal, 
  Timeline, 
  Button, 
  Space, 
  Tag, 
  Typography, 
  Card, 
  Divider,
  message,
  Popconfirm,
  Tooltip
} from 'antd';
import { 
  HistoryOutlined,
  RollbackOutlined,
  EyeOutlined,
  SwapOutlined,
  UserOutlined,
  ClockCircleOutlined
} from '@ant-design/icons';

const { Text, Paragraph } = Typography;

interface Version {
  id: string;
  version: string;
  title: string;
  content: string;
  author: string;
  createdAt: string;
  description: string;
  isCurrent: boolean;
}

interface VersionControlProps {
  visible: boolean;
  onClose: () => void;
  documentId: number;
  currentVersion?: Version;
  onRevert?: (version: Version) => void;
}

const VersionControl: React.FC<VersionControlProps> = ({
  visible,
  onClose,
  documentId,
  currentVersion,
  onRevert
}) => {
  const [selectedVersion, setSelectedVersion] = useState<Version | null>(null);
  const [compareMode, setCompareMode] = useState(false);
  const [compareVersion, setCompareVersion] = useState<Version | null>(null);

  // 模拟版本数据
  const versions: Version[] = [
    {
      id: 'v1.3',
      version: '1.3',
      title: '快速开始指南',
      content: '这是最新版本的文档内容，包含了完整的快速开始指南...',
      author: '张三',
      createdAt: '2024-01-15 14:30',
      description: '更新了API接口说明，修复了部分错误',
      isCurrent: true,
    },
    {
      id: 'v1.2',
      version: '1.2',
      title: '快速开始指南',
      content: '这是1.2版本的文档内容，包含了基础的快速开始指南...',
      author: '李四',
      createdAt: '2024-01-14 10:15',
      description: '添加了新的功能说明',
      isCurrent: false,
    },
    {
      id: 'v1.1',
      version: '1.1',
      title: '快速开始指南',
      content: '这是1.1版本的文档内容，包含了简单的快速开始指南...',
      author: '王五',
      createdAt: '2024-01-13 16:45',
      description: '修复了格式问题',
      isCurrent: false,
    },
    {
      id: 'v1.0',
      version: '1.0',
      title: '快速开始指南',
      content: '这是1.0版本的文档内容，初始版本...',
      author: '赵六',
      createdAt: '2024-01-12 09:20',
      description: '初始版本',
      isCurrent: false,
    },
  ];

  // 处理版本回滚
  const handleRevert = (version: Version) => {
    Modal.confirm({
      title: '确认回滚',
      content: `确定要回滚到版本 ${version.version} 吗？这将覆盖当前版本的内容。`,
      onOk: () => {
        onRevert?.(version);
        message.success(`已回滚到版本 ${version.version}`);
      },
    });
  };

  // 处理版本对比
  const handleCompare = (version: Version) => {
    setCompareVersion(version);
    setCompareMode(true);
  };

  // 渲染版本对比
  const renderVersionCompare = () => {
    if (!compareVersion || !currentVersion) return null;

    return (
      <div style={{ display: 'flex', gap: 16 }}>
        <div style={{ flex: 1 }}>
          <Card title={`版本 ${compareVersion.version} (${compareVersion.createdAt})`} size="small">
            <div style={{ 
              padding: 16, 
              backgroundColor: '#f5f5f5', 
              borderRadius: 6,
              maxHeight: 400,
              overflow: 'auto'
            }}>
              <Paragraph>{compareVersion.content}</Paragraph>
            </div>
          </Card>
        </div>
        <div style={{ flex: 1 }}>
          <Card title={`当前版本 ${currentVersion.version} (${currentVersion.createdAt})`} size="small">
            <div style={{ 
              padding: 16, 
              backgroundColor: '#f5f5f5', 
              borderRadius: 6,
              maxHeight: 400,
              overflow: 'auto'
            }}>
              <Paragraph>{currentVersion.content}</Paragraph>
            </div>
          </Card>
        </div>
      </div>
    );
  };

  return (
    <Modal
      title="版本历史"
      open={visible}
      onCancel={onClose}
      width={800}
      footer={null}
    >
      {compareMode ? (
        <div>
          <div style={{ marginBottom: 16 }}>
            <Button 
              icon={<HistoryOutlined />} 
              onClick={() => setCompareMode(false)}
            >
              返回版本列表
            </Button>
          </div>
          {renderVersionCompare()}
        </div>
      ) : (
        <div>
          <div style={{ marginBottom: 16 }}>
            <Text type="secondary">
              文档ID: {documentId} • 共 {versions.length} 个版本
            </Text>
          </div>

          <Timeline>
            {versions.map((version) => (
              <Timeline.Item
                key={version.id}
                dot={version.isCurrent ? <HistoryOutlined style={{ color: '#1890ff' }} /> : undefined}
              >
                <Card size="small" style={{ marginBottom: 16 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                    <div>
                      <Space>
                        <Text strong>版本 {version.version}</Text>
                        {version.isCurrent && <Tag color="blue">当前版本</Tag>}
                      </Space>
                    </div>
                    <Space>
                      <Tooltip title="查看版本">
                        <Button 
                          type="text" 
                          size="small" 
                          icon={<EyeOutlined />}
                          onClick={() => setSelectedVersion(version)}
                        />
                      </Tooltip>
                      {!version.isCurrent && (
                        <>
                          <Tooltip title="版本对比">
                            <Button 
                              type="text" 
                              size="small" 
                              icon={<SwapOutlined />}
                              onClick={() => handleCompare(version)}
                            />
                          </Tooltip>
                          <Popconfirm
                            title="确认回滚"
                            description={`确定要回滚到版本 ${version.version} 吗？`}
                            onConfirm={() => handleRevert(version)}
                          >
                            <Tooltip title="回滚到此版本">
                              <Button 
                                type="text" 
                                size="small" 
                                icon={<RollbackOutlined />}
                                danger
                              />
                            </Tooltip>
                          </Popconfirm>
                        </>
                      )}
                    </Space>
                  </div>

                  <div style={{ marginBottom: 8 }}>
                    <Text type="secondary">
                      <UserOutlined /> {version.author} • 
                      <ClockCircleOutlined /> {version.createdAt}
                    </Text>
                  </div>

                  <div style={{ marginBottom: 8 }}>
                    <Text>{version.description}</Text>
                  </div>

                  <div style={{ 
                    padding: 8, 
                    backgroundColor: '#f8f9fa', 
                    borderRadius: 4,
                    fontSize: 12,
                    color: '#666',
                    maxHeight: 60,
                    overflow: 'hidden'
                  }}>
                    {version.content.substring(0, 100)}...
                  </div>
                </Card>
              </Timeline.Item>
            ))}
          </Timeline>

          {/* 版本详情弹窗 */}
          <Modal
            title={`版本 ${selectedVersion?.version} 详情`}
            open={!!selectedVersion}
            onCancel={() => setSelectedVersion(null)}
            footer={null}
            width={600}
          >
            {selectedVersion && (
              <div>
                <div style={{ marginBottom: 16 }}>
                  <Text type="secondary">
                    <UserOutlined /> {selectedVersion.author} • 
                    <ClockCircleOutlined /> {selectedVersion.createdAt}
                  </Text>
                </div>
                <div style={{ marginBottom: 16 }}>
                  <Text strong>更新说明：</Text>
                  <Paragraph>{selectedVersion.description}</Paragraph>
                </div>
                <Divider />
                <div style={{ 
                  padding: 16, 
                  backgroundColor: '#f8f9fa', 
                  borderRadius: 6,
                  maxHeight: 400,
                  overflow: 'auto'
                }}>
                  <Paragraph>{selectedVersion.content}</Paragraph>
                </div>
              </div>
            )}
          </Modal>
        </div>
      )}
    </Modal>
  );
};

export default VersionControl; 