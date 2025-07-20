import React, { useState } from 'react';
import { 
  Modal, 
  Button, 
  Space, 
  Typography, 
  Card, 
  Progress, 
  List, 
  Tag,
  message,
  Upload,
  Alert,
  Divider,
  Statistic,
  Row,
  Col
} from 'antd';
import { 
  UploadOutlined,
  DownloadOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  ClockCircleOutlined,
  DeleteOutlined
} from '@ant-design/icons';
import { DataManager as StorageDataManager } from '../services/storage';

const { Title, Text, Paragraph } = Typography;
const { Dragger } = Upload;

interface DataManagerProps {
  visible: boolean;
  onClose: () => void;
}

interface BackupInfo {
  id: string;
  name: string;
  size: number;
  createdAt: string;
  itemCount: {
    documents: number;
    qa: number;
    categories: number;
    comments: number;
  };
}

const DataManager: React.FC<DataManagerProps> = ({
  visible,
  onClose
}) => {
  const [backups, setBackups] = useState<BackupInfo[]>([]);
  const [isBackingUp, setIsBackingUp] = useState(false);
  const [isRestoring, setIsRestoring] = useState(false);
  const [backupProgress, setBackupProgress] = useState(0);
  const [restoreProgress, setRestoreProgress] = useState(0);

  // 创建备份
  const handleCreateBackup = async () => {
    setIsBackingUp(true);
    setBackupProgress(0);

    try {
      // 模拟备份过程
      for (let i = 0; i <= 100; i += 10) {
        setBackupProgress(i);
        await new Promise(resolve => setTimeout(resolve, 100));
      }

      // 执行实际备份
      StorageDataManager.backup();

      // 添加到备份列表
      const newBackup: BackupInfo = {
        id: Date.now().toString(),
        name: `备份_${new Date().toLocaleString()}`,
        size: Math.floor(Math.random() * 1000000) + 100000, // 模拟文件大小
        createdAt: new Date().toISOString(),
        itemCount: {
          documents: StorageDataManager.getKnowledgeEntries().length,
          qa: StorageDataManager.getQAPairs().length,
          categories: StorageDataManager.getCategories().length,
          comments: StorageDataManager.getComments().length,
        },
      };

      setBackups(prev => [newBackup, ...prev]);
      message.success('备份创建成功');
    } catch (error) {
      message.error('备份创建失败');
    } finally {
      setIsBackingUp(false);
      setBackupProgress(0);
    }
  };

  // 恢复备份
  const handleRestore = async (file: File) => {
    setIsRestoring(true);
    setRestoreProgress(0);

    try {
      // 模拟恢复过程
      for (let i = 0; i <= 100; i += 20) {
        setRestoreProgress(i);
        await new Promise(resolve => setTimeout(resolve, 200));
      }

      // 执行实际恢复
      const success = await StorageDataManager.restore(file);
      
      if (success) {
        message.success('数据恢复成功');
        // 刷新页面以应用恢复的数据
        window.location.reload();
      } else {
        message.error('数据恢复失败');
      }
    } catch (error) {
      message.error('数据恢复失败');
    } finally {
      setIsRestoring(false);
      setRestoreProgress(0);
    }
  };

  // 删除备份
  const handleDeleteBackup = (backupId: string) => {
    setBackups(prev => prev.filter(backup => backup.id !== backupId));
    message.success('备份已删除');
  };

  // 导出数据
  const handleExportData = () => {
    try {
      StorageDataManager.backup();
      message.success('数据导出成功');
    } catch (error) {
      message.error('数据导出失败');
    }
  };

  // 获取存储统计信息
  const getStorageStats = () => {
    const documents = StorageDataManager.getKnowledgeEntries();
    const qa = StorageDataManager.getQAPairs();
    const categories = StorageDataManager.getCategories();
    const comments = StorageDataManager.getComments();
    const versions = StorageDataManager.getVersions();

    return {
      documents: documents.length,
      qa: qa.length,
      categories: categories.length,
      comments: comments.length,
      versions: versions.length,
      totalSize: JSON.stringify({
        documents,
        qa,
        categories,
        comments,
        versions,
      }).length,
    };
  };

  const stats = getStorageStats();

  return (
    <Modal
      title="数据管理"
      open={visible}
      onCancel={onClose}
      width={800}
      footer={null}
    >
      {/* 存储统计 */}
      <Card title="存储统计" style={{ marginBottom: 16 }}>
        <Row gutter={16}>
          <Col span={6}>
            <Statistic
              title="文档数量"
              value={stats.documents}
              prefix={<FileTextOutlined />}
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="问答数量"
              value={stats.qa}
              prefix={<DatabaseOutlined />}
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="分类数量"
              value={stats.categories}
              prefix={<FileTextOutlined />}
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="评论数量"
              value={stats.comments}
              prefix={<DatabaseOutlined />}
            />
          </Col>
        </Row>
        <div style={{ marginTop: 16 }}>
          <Text type="secondary">
            总数据大小: {(stats.totalSize / 1024).toFixed(2)} KB
          </Text>
        </div>
      </Card>

      {/* 备份操作 */}
      <Card title="数据备份" style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <div>
            <Button
              type="primary"
              icon={<DownloadOutlined />}
              onClick={handleCreateBackup}
              loading={isBackingUp}
              style={{ marginRight: 8 }}
            >
              创建备份
            </Button>
            <Button
              icon={<UploadOutlined />}
              onClick={handleExportData}
            >
              导出数据
            </Button>
          </div>

          {isBackingUp && (
            <div>
              <Text>正在创建备份...</Text>
              <Progress percent={backupProgress} size="small" />
            </div>
          )}
        </Space>
      </Card>

      {/* 数据恢复 */}
      <Card title="数据恢复" style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Alert
            message="数据恢复警告"
            description="恢复数据将覆盖当前所有数据，请确保已备份重要数据。"
            type="warning"
            showIcon
            style={{ marginBottom: 16 }}
          />

          <Dragger
            accept=".json"
            beforeUpload={(file) => {
              handleRestore(file);
              return false; // 阻止自动上传
            }}
            disabled={isRestoring}
          >
            <p className="ant-upload-drag-icon">
              <UploadOutlined />
            </p>
            <p className="ant-upload-text">点击或拖拽文件到此区域上传</p>
            <p className="ant-upload-hint">
              支持 .json 格式的备份文件
            </p>
          </Dragger>

          {isRestoring && (
            <div>
              <Text>正在恢复数据...</Text>
              <Progress percent={restoreProgress} size="small" />
            </div>
          )}
        </Space>
      </Card>

      {/* 备份历史 */}
      <Card title="备份历史">
        <List
          dataSource={backups}
          renderItem={(backup) => (
            <List.Item
              actions={[
                <Button
                  key="download"
                  type="link"
                  icon={<DownloadOutlined />}
                  onClick={() => handleExportData()}
                >
                  下载
                </Button>,
                <Button
                  key="delete"
                  type="link"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={() => handleDeleteBackup(backup.id)}
                >
                  删除
                </Button>,
              ]}
            >
              <List.Item.Meta
                title={
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span>{backup.name}</span>
                    <Tag color="green" icon={<CheckCircleOutlined />}>
                      成功
                    </Tag>
                  </div>
                }
                description={
                  <div>
                    <div style={{ marginBottom: 4 }}>
                      <ClockCircleOutlined style={{ marginRight: 4 }} />
                      {new Date(backup.createdAt).toLocaleString()}
                    </div>
                    <div style={{ fontSize: 12, color: '#666' }}>
                      文档: {backup.itemCount.documents} | 
                      问答: {backup.itemCount.qa} | 
                      分类: {backup.itemCount.categories} | 
                      评论: {backup.itemCount.comments}
                    </div>
                    <div style={{ fontSize: 12, color: '#666' }}>
                      文件大小: {(backup.size / 1024).toFixed(2)} KB
                    </div>
                  </div>
                }
              />
            </List.Item>
          )}
        />
      </Card>
    </Modal>
  );
};

export default DataManager; 