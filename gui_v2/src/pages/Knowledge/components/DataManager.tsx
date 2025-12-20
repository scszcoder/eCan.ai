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
  Statistic,
  Row,
  Col,
  theme
} from 'antd';
import { 
  UploadOutlined,
  DownloadOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  DeleteOutlined
} from '@ant-design/icons';
import { DataManager as StorageDataManager } from '../services/storage';
import { useTranslation } from 'react-i18next';

const { Text } = Typography;
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
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const [backups, setBackups] = useState<BackupInfo[]>([]);
  const [isBackingUp, setIsBackingUp] = useState(false);
  const [isRestoring, setIsRestoring] = useState(false);
  const [backupProgress, setBackupProgress] = useState(0);
  const [restoreProgress, setRestoreProgress] = useState(0);

  // CreateBackup
  const handleCreateBackup = async () => {
    setIsBackingUp(true);
    setBackupProgress(0);

    try {
      // 模拟Backup过程
      for (let i = 0; i <= 100; i += 10) {
        setBackupProgress(i);
        await new Promise(resolve => setTimeout(resolve, 100));
      }

      // Execute实际Backup
      StorageDataManager.backup();

      // Add到BackupList
      const newBackup: BackupInfo = {
        id: Date.now().toString(),
        name: `Backup_${new Date().toLocaleString()}`,
        size: Math.floor(Math.random() * 1000000) + 100000, // 模拟文件Size
        createdAt: new Date().toISOString(),
        itemCount: {
          documents: StorageDataManager.getKnowledgeEntries().length,
          qa: StorageDataManager.getQAPairs().length,
          categories: StorageDataManager.getCategories().length,
          comments: StorageDataManager.getComments().length,
        },
      };

      setBackups(prev => [newBackup, ...prev]);
      message.success('BackupCreateSuccess');
    } catch (error) {
      message.error('BackupCreateFailed');
    } finally {
      setIsBackingUp(false);
      setBackupProgress(0);
    }
  };

  // RestoreBackup
  const handleRestore = async (file: File) => {
    setIsRestoring(true);
    setRestoreProgress(0);

    try {
      // 模拟Restore过程
      for (let i = 0; i <= 100; i += 20) {
        setRestoreProgress(i);
        await new Promise(resolve => setTimeout(resolve, 200));
      }

      // Execute实际Restore
      const success = await StorageDataManager.restore(file);
      
      if (success) {
        message.success('DataRestoreSuccess');
        // RefreshPage以应用Restore的Data
        window.location.reload();
      } else {
        message.error('DataRestoreFailed');
      }
    } catch (error) {
      message.error('DataRestoreFailed');
    } finally {
      setIsRestoring(false);
      setRestoreProgress(0);
    }
  };

  // DeleteBackup
  const handleDeleteBackup = (backupId: string) => {
    setBackups(prev => prev.filter(backup => backup.id !== backupId));
    message.success('Backup已Delete');
  };

  // ExportData
  const handleExportData = () => {
    try {
      StorageDataManager.backup();
      message.success('DataExportSuccess');
    } catch (error) {
      message.error('DataExportFailed');
    }
  };

  // GetStorage统计Information
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
      title={t('pages.knowledge.dataManagement')}
      open={visible}
      onCancel={onClose}
      width={800}
      footer={null}
      styles={{
        body: { backgroundColor: token.colorBgContainer }
      }}
    >
      {/* Storage统计 */}
      <Card title="Storage统计" style={{ marginBottom: 16, backgroundColor: token.colorBgElevated }}>
        <Row gutter={16}>
          <Col span={6}>
            <Statistic
              title="DocumentationCount"
              value={stats.documents}
              prefix={<FileTextOutlined />}
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="问答Count"
              value={stats.qa}
              prefix={<DatabaseOutlined />}
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="CategoryCount"
              value={stats.categories}
              prefix={<FileTextOutlined />}
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="评论Count"
              value={stats.comments}
              prefix={<DatabaseOutlined />}
            />
          </Col>
        </Row>
        <div style={{ marginTop: 16 }}>
          <Text type="secondary">
            总DataSize: {(stats.totalSize / 1024).toFixed(2)} KB
          </Text>
        </div>
      </Card>

      {/* BackupOperation */}
      <Card title="DataBackup" style={{ marginBottom: 16, backgroundColor: token.colorBgElevated }}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <div>
            <Button
              type="primary"
              icon={<DownloadOutlined />}
              onClick={handleCreateBackup}
              loading={isBackingUp}
              style={{ marginRight: 8 }}
            >
              CreateBackup
            </Button>
            <Button
              icon={<UploadOutlined />}
              onClick={handleExportData}
            >
              ExportData
            </Button>
          </div>

          {isBackingUp && (
            <div>
              <Text>正在CreateBackup...</Text>
              <Progress percent={backupProgress} size="small" />
            </div>
          )}
        </Space>
      </Card>

      {/* DataRestore */}
      <Card title="DataRestore" style={{ marginBottom: 16, backgroundColor: token.colorBgElevated }}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Alert
            message="DataRestoreWarning"
            description="RestoreData将覆盖When前AllData，请确保已Backup重要Data。"
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
            <p className="ant-upload-text">Click或Drag文件到此区域上传</p>
            <p className="ant-upload-hint">
              Support .json 格式的Backup文件
            </p>
          </Dragger>

          {isRestoring && (
            <div>
              <Text>正在RestoreData...</Text>
              <Progress percent={restoreProgress} size="small" />
            </div>
          )}
        </Space>
      </Card>

      {/* Backup历史 */}
      <Card title="Backup历史" style={{ backgroundColor: token.colorBgElevated }}>
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
                  Delete
                </Button>,
              ]}
            >
              <List.Item.Meta
                title={
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span>{backup.name}</span>
                    <Tag color="green" icon={<CheckCircleOutlined />}>
                      Success
                    </Tag>
                  </div>
                }
                description={
                  <div>
                    <div style={{ marginBottom: 4 }}>
                      <ClockCircleOutlined style={{ marginRight: 4 }} />
                      {new Date(backup.createdAt).toLocaleString()}
                    </div>
                    <div style={{ fontSize: 12, color: token.colorTextSecondary }}>
                      Documentation: {backup.itemCount.documents} | 
                      问答: {backup.itemCount.qa} | 
                      Category: {backup.itemCount.categories} | 
                      评论: {backup.itemCount.comments}
                    </div>
                    <div style={{ fontSize: 12, color: token.colorTextSecondary }}>
                      文件Size: {(backup.size / 1024).toFixed(2)} KB
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