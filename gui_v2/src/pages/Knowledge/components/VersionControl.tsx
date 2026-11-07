import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation();
  const [compareMode, setCompareMode] = useState(false);
  const [compareVersion, setCompareVersion] = useState<Version | null>(null);

  // 模拟VersionData
  const versions: Version[] = [
    {
      id: 'v1.3',
      version: '1.3',
      title: t('pages.knowledge.versionControl.startGuideTitle'),
      content: t('pages.knowledge.versionControl.contentLatest'),
      author: t('pages.knowledge.versionControl.authors.zhangSan'),
      createdAt: '2024-01-15 14:30',
      description: t('pages.knowledge.versionControl.descV13'),
      isCurrent: true,
    },
    {
      id: 'v1.2',
      version: '1.2',
      title: t('pages.knowledge.versionControl.startGuideTitle'),
      content: t('pages.knowledge.versionControl.contentV12'),
      author: t('pages.knowledge.versionControl.authors.liSi'),
      createdAt: '2024-01-14 10:15',
      description: t('pages.knowledge.versionControl.descV12'),
      isCurrent: false,
    },
    {
      id: 'v1.1',
      version: '1.1',
      title: t('pages.knowledge.versionControl.startGuideTitle'),
      content: t('pages.knowledge.versionControl.contentV11'),
      author: t('pages.knowledge.versionControl.authors.wangWu'),
      createdAt: '2024-01-13 16:45',
      description: t('pages.knowledge.versionControl.descV11'),
      isCurrent: false,
    },
    {
      id: 'v1.0',
      version: '1.0',
      title: t('pages.knowledge.versionControl.startGuideTitle'),
      content: t('pages.knowledge.versionControl.contentV10'),
      author: t('pages.knowledge.versionControl.authors.zhaoLiu'),
      createdAt: '2024-01-12 09:20',
      description: t('pages.knowledge.versionControl.descV10'),
      isCurrent: false,
    },
  ];

  // ProcessVersion回滚
  const handleRevert = (version: Version) => {
    Modal.confirm({
      title: t('pages.knowledge.versionControl.revertConfirmTitle'),
      content: t('pages.knowledge.versionControl.revertConfirmContent', { version: version.version }),
      onOk: () => {
        onRevert?.(version);
        message.success(t('pages.knowledge.versionControl.revertSuccess', { version: version.version }));
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
              backgroundColor: 'var(--bg-sunken)',
              borderRadius: 'var(--radius-xs-tight)',
              maxHeight: 400,
              overflowX: 'hidden',
              overflowY: 'auto'
            }}>
              <Paragraph>{compareVersion.content}</Paragraph>
            </div>
          </Card>
        </div>
        <div style={{ flex: 1 }}>
          <Card title={t('pages.knowledge.versionControl.currentVersionCardTitle', { version: currentVersion.version, createdAt: currentVersion.createdAt })} size="small">
            <div style={{
              padding: 16,
              backgroundColor: 'var(--bg-sunken)',
              borderRadius: 'var(--radius-xs-tight)',
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
      title={t('pages.knowledge.versionControl.historyTitle')}
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
              {t('pages.knowledge.versionControl.backToList')}
            </Button>
          </div>
          {renderVersionCompare()}
        </div>
      ) : (
        <div>
          <div style={{ marginBottom: 16 }}>
            <Text type="secondary">
              {t('pages.knowledge.versionControl.summary', { id: documentId, count: versions.length })}
            </Text>
          </div>

          <Timeline>
            {versions.map((version) => (
              <Timeline.Item
                key={version.id}
                dot={version.isCurrent ? <HistoryOutlined style={{ color: 'var(--primary-text)' }} /> : undefined}
              >
                <Card size="small" style={{ marginBottom: 16 }} key={version.id + '-card'}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                    <div>
                      <Space>
                        <Text strong>Version {version.version}</Text>
                        {version.isCurrent && <Tag color="blue">{t('pages.knowledge.versionControl.currentVersionTag')}</Tag>}
                      </Space>
                    </div>
                    <Space>
                      <Tooltip title={t('pages.knowledge.versionControl.viewVersion')}>
                        <Button 
                          type="text" 
                          size="small" 
                          icon={<EyeOutlined />}
                          onClick={() => setSelectedVersion(version)}
                        />
                      </Tooltip>
                      {!version.isCurrent && (
                        <>
                          <Tooltip title={t('pages.knowledge.versionControl.compareVersion')}>
                            <Button 
                              type="text" 
                              size="small" 
                              icon={<SwapOutlined />}
                              onClick={() => handleCompare(version)}
                            />
                          </Tooltip>
                          <Popconfirm
                            title={t('pages.knowledge.versionControl.revertConfirmTitleShort')}
                            description={t('pages.knowledge.versionControl.revertConfirmDescription', { version: version.version })}
                            onConfirm={() => handleRevert(version)}
                          >
                            <Tooltip title={t('pages.knowledge.versionControl.revertToThisVersion')}>
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
                    borderRadius: 'var(--radius-xs)',
                    fontSize: 'var(--font-size-sm)',
                    color: 'var(--text-secondary)',
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
                  <Text strong>{t('pages.knowledge.versionControl.updateDescription')}</Text>
                  <Paragraph>{selectedVersion.description}</Paragraph>
                </div>
                <Divider />
                <div style={{
                  padding: 16,
                  backgroundColor: '#f8f9fa',
                  borderRadius: 'var(--radius-xs-tight)',
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