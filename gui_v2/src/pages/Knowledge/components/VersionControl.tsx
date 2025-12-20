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

  // 模拟VersionData
  const versions: Version[] = [
    {
      id: 'v1.3',
      version: '1.3',
      title: 'Fast开始指南',
      content: '这是最新Version的DocumentationContent，Include了完整的Fast开始指南...',
      author: '张三',
      createdAt: '2024-01-15 14:30',
      description: 'Update了APIInterface说明，FIX了部分Error',
      isCurrent: true,
    },
    {
      id: 'v1.2',
      version: '1.2',
      title: 'Fast开始指南',
      content: '这是1.2Version的DocumentationContent，Include了Base的Fast开始指南...',
      author: '李四',
      createdAt: '2024-01-14 10:15',
      description: 'Add了新的功能说明',
      isCurrent: false,
    },
    {
      id: 'v1.1',
      version: '1.1',
      title: 'Fast开始指南',
      content: '这是1.1Version的DocumentationContent，Include了Simple的Fast开始指南...',
      author: '王五',
      createdAt: '2024-01-13 16:45',
      description: 'FIX了格式问题',
      isCurrent: false,
    },
    {
      id: 'v1.0',
      version: '1.0',
      title: 'Fast开始指南',
      content: '这是1.0Version的DocumentationContent，初始Version...',
      author: '赵六',
      createdAt: '2024-01-12 09:20',
      description: '初始Version',
      isCurrent: false,
    },
  ];

  // ProcessVersion回滚
  const handleRevert = (version: Version) => {
    Modal.confirm({
      title: 'Confirm回滚',
      content: `确定要回滚到Version ${version.version} 吗？这将覆盖When前Version的Content。`,
      onOk: () => {
        onRevert?.(version);
        message.success(`已回滚到Version ${version.version}`);
      },
    });
  };

  // ProcessVersion对比
  const handleCompare = (version: Version) => {
    setCompareVersion(version);
    setCompareMode(true);
  };

  // RenderVersion对比
  const renderVersionCompare = () => {
    if (!compareVersion || !currentVersion) return null;

    return (
      <div style={{ display: 'flex', gap: 16 }}>
        <div style={{ flex: 1 }}>
          <Card title={`Version ${compareVersion.version} (${compareVersion.createdAt})`} size="small">
            <div style={{
              padding: 16,
              backgroundColor: '#f5f5f5',
              borderRadius: 6,
              maxHeight: 400,
              overflowX: 'hidden',
              overflowY: 'auto'
            }}>
              <Paragraph>{compareVersion.content}</Paragraph>
            </div>
          </Card>
        </div>
        <div style={{ flex: 1 }}>
          <Card title={`When前Version ${currentVersion.version} (${currentVersion.createdAt})`} size="small">
            <div style={{
              padding: 16,
              backgroundColor: '#f5f5f5',
              borderRadius: 6,
              maxHeight: 400,
              overflowX: 'hidden',
              overflowY: 'auto'
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
      title="Version历史"
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
              返回VersionList
            </Button>
          </div>
          {renderVersionCompare()}
        </div>
      ) : (
        <div>
          <div style={{ marginBottom: 16 }}>
            <Text type="secondary">
              DocumentationID: {documentId} • 共 {versions.length} 个Version
            </Text>
          </div>

          <Timeline>
            {versions.map((version) => (
              <Timeline.Item
                key={version.id}
                dot={version.isCurrent ? <HistoryOutlined style={{ color: '#1890ff' }} /> : undefined}
              >
                <Card size="small" style={{ marginBottom: 16 }} key={version.id + '-card'}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                    <div>
                      <Space>
                        <Text strong>Version {version.version}</Text>
                        {version.isCurrent && <Tag color="blue">When前Version</Tag>}
                      </Space>
                    </div>
                    <Space>
                      <Tooltip title="查看Version">
                        <Button 
                          type="text" 
                          size="small" 
                          icon={<EyeOutlined />}
                          onClick={() => setSelectedVersion(version)}
                        />
                      </Tooltip>
                      {!version.isCurrent && (
                        <>
                          <Tooltip title="Version对比">
                            <Button 
                              type="text" 
                              size="small" 
                              icon={<SwapOutlined />}
                              onClick={() => handleCompare(version)}
                            />
                          </Tooltip>
                          <Popconfirm
                            title="Confirm回滚"
                            description={`确定要回滚到Version ${version.version} 吗？`}
                            onConfirm={() => handleRevert(version)}
                          >
                            <Tooltip title="回滚到此Version">
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

          {/* VersionDetailsModal */}
          <Modal
            title={`Version ${selectedVersion?.version} Details`}
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
                  <Text strong>Update说明：</Text>
                  <Paragraph>{selectedVersion.description}</Paragraph>
                </div>
                <Divider />
                <div style={{
                  padding: 16,
                  backgroundColor: '#f8f9fa',
                  borderRadius: 6,
                  maxHeight: 400,
                  overflowX: 'hidden',
                  overflowY: 'auto'
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