import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Card,
  Button,
  Upload,
  Table,
  Space,
  Tag,
  Input,
  Typography,
  message,
  Modal,
  Progress,
  Empty,
  Tooltip,
  Row,
  Col,
  Tabs,
  Collapse,
  Spin,
  theme,
} from 'antd';
import {
  UploadOutlined,
  DeleteOutlined,
  SearchOutlined,
  SyncOutlined,
  ThunderboltOutlined,
  FileTextOutlined,
  FilePdfOutlined,
  FileImageOutlined,
  FileExcelOutlined,
  FileWordOutlined,
  CloudUploadOutlined,
  ReloadOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  DatabaseOutlined,
  SendOutlined,
  RobotOutlined,
  UserOutlined,
  ClearOutlined,
  FileSearchOutlined,
} from '@ant-design/icons';
import type { UploadFile } from 'antd';
import {
  useRAGStore,
  type RAGDocument,
  type RAGChunk,
  type RAGChatMessage,
} from '../../stores/ragStore';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

// ── helpers ────────────────────────────────────────────────────────────
function fileIcon(name: string) {
  const ext = name.split('.').pop()?.toLowerCase();
  switch (ext) {
    case 'pdf': return <FilePdfOutlined style={{ color: '#e74c3c' }} />;
    case 'png': case 'jpg': case 'jpeg': case 'gif': case 'webp':
      return <FileImageOutlined style={{ color: '#3498db' }} />;
    case 'xls': case 'xlsx': case 'csv':
      return <FileExcelOutlined style={{ color: '#27ae60' }} />;
    case 'doc': case 'docx':
      return <FileWordOutlined style={{ color: '#2980b9' }} />;
    default: return <FileTextOutlined style={{ color: '#95a5a6' }} />;
  }
}

function statusTag(status: string) {
  switch (status) {
    case 'uploaded': return <Tag color="blue">Uploaded</Tag>;
    case 'indexed': return <Tag color="green">Indexed</Tag>;
    case 'error': return <Tag color="red">Error</Tag>;
    default: return <Tag>{status}</Tag>;
  }
}

function indexStatusBadge(status: string) {
  switch (status) {
    case 'ready': return <Tag icon={<CheckCircleOutlined />} color="success">Ready</Tag>;
    case 'indexing': return <Tag icon={<SyncOutlined spin />} color="processing">Indexing</Tag>;
    case 'error': return <Tag icon={<ExclamationCircleOutlined />} color="error">Error</Tag>;
    default: return <Tag icon={<ClockCircleOutlined />} color="default">No Index</Tag>;
  }
}

function formatFileSize(bytes: number) {
  if (!bytes) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ── Chat bubble component ──────────────────────────────────────────────
const ChatBubble: React.FC<{ msg: RAGChatMessage; token: any }> = ({ msg, token }) => {
  const isUser = msg.role === 'user';

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: isUser ? 'flex-end' : 'flex-start',
        marginBottom: 16,
        gap: 8,
        alignItems: 'flex-start',
      }}
    >
      {!isUser && (
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: '50%',
            background: token.colorPrimary,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          <RobotOutlined style={{ color: '#fff', fontSize: 16 }} />
        </div>
      )}
      <div style={{ maxWidth: '80%', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {/* Main message bubble */}
        <div
          style={{
            padding: '10px 14px',
            borderRadius: isUser ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
            background: isUser ? token.colorPrimary : token.colorBgElevated,
            color: isUser ? '#fff' : token.colorText,
            fontSize: 14,
            lineHeight: 1.6,
            whiteSpace: 'pre-wrap',
            boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
          }}
        >
          {msg.content}
        </div>

        {/* Source chunks (expandable) */}
        {!isUser && msg.chunks && msg.chunks.length > 0 && (
          <Collapse
            ghost
            size="small"
            items={[{
              key: '1',
              label: (
                <Space size={4}>
                  <FileSearchOutlined />
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {msg.chunks.length} source{msg.chunks.length > 1 ? 's' : ''} used
                  </Text>
                </Space>
              ),
              children: (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {msg.chunks.map((chunk: RAGChunk, i: number) => (
                    <div
                      key={i}
                      style={{
                        padding: '8px 10px',
                        background: token.colorFillQuaternary,
                        borderRadius: 8,
                        borderLeft: `3px solid ${token.colorPrimary}`,
                        fontSize: 12,
                      }}
                    >
                      <Paragraph
                        ellipsis={{ rows: 3, expandable: true }}
                        style={{ margin: 0, fontSize: 12 }}
                      >
                        {chunk.text}
                      </Paragraph>
                      <Space style={{ marginTop: 4 }}>
                        <Tag color="blue" style={{ fontSize: 10 }}>{chunk.source || 'unknown'}</Tag>
                        <Text type="secondary" style={{ fontSize: 10 }}>
                          relevance: {chunk.score.toFixed(2)}
                        </Text>
                      </Space>
                    </div>
                  ))}
                </div>
              ),
            }]}
          />
        )}

        <Text type="secondary" style={{ fontSize: 10, alignSelf: isUser ? 'flex-end' : 'flex-start' }}>
          {new Date(msg.timestamp).toLocaleTimeString()}
        </Text>
      </div>

      {isUser && (
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: '50%',
            background: token.colorTextQuaternary,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          <UserOutlined style={{ color: '#fff', fontSize: 16 }} />
        </div>
      )}
    </div>
  );
};

// ── Main component ─────────────────────────────────────────────────────
const RAGDocuments: React.FC = () => {
  const { token } = theme.useToken();
  const [pid] = useState('default');
  const [queryText, setQueryText] = useState('');
  const [selectedDocs, setSelectedDocs] = useState<string[]>([]);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [activeTab, setActiveTab] = useState('docs');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const {
    documents, indexStatus, chatHistory,
    loading, uploading, uploadProgress, indexing, querying, error,
    fetchDocs, fetchIndexStatus, uploadFiles, triggerIndex, deleteDocs, query,
    clearChat,
  } = useRAGStore();

  // Initial fetch
  useEffect(() => {
    fetchDocs(pid);
    fetchIndexStatus(pid);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid]);

  // Poll index status while indexing
  useEffect(() => {
    if (indexStatus?.status === 'indexing') {
      pollRef.current = setInterval(() => fetchIndexStatus(pid), 10_000);
    } else {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [indexStatus?.status, pid]);

  // Auto-scroll chat
  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [chatHistory.length, querying]);

  // ── Upload handler ─────────────────────────────────────────────────
  const handleUpload = useCallback(async () => {
    const files = fileList.map(f => f.originFileObj).filter(Boolean) as File[];
    if (!files.length) { message.warning('Select files first'); return; }
    const success = await uploadFiles(files, pid);
    if (success) {
      message.success(`Uploaded ${files.length} file(s)`);
      setFileList([]);
    } else {
      message.error(useRAGStore.getState().error || 'Upload failed');
    }
  }, [fileList, pid, uploadFiles]);

  // ── Delete handler ────────────────────────────────────────────────
  const handleDelete = useCallback((docKeys: string[]) => {
    Modal.confirm({
      title: `Delete ${docKeys.length} document(s)?`,
      content: 'This will remove the files from storage. The search index may need to be rebuilt.',
      okText: 'Delete',
      okType: 'danger',
      onOk: async () => {
        await deleteDocs(docKeys, pid);
        setSelectedDocs([]);
        message.success('Deleted');
      },
    });
  }, [deleteDocs, pid]);

  // ── Index handler ──────────────────────────────────────────────────
  const handleIndex = useCallback(async () => {
    const started = await triggerIndex(pid);
    if (started) message.info('Indexing started — this may take a few minutes');
    else message.error(useRAGStore.getState().error || 'Unable to start indexing');
  }, [triggerIndex, pid]);

  // ── Chat send handler ─────────────────────────────────────────────
  const handleSend = useCallback(async () => {
    const q = queryText.trim();
    if (!q) return;
    setQueryText('');
    await query(q, pid);
  }, [query, queryText, pid]);

  // Handle Enter key (send on Enter, newline on Shift+Enter)
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  // ── Table columns ──────────────────────────────────────────────────
  const columns = [
    {
      title: 'File',
      dataIndex: 'fileName',
      key: 'fileName',
      render: (name: string) => (
        <Space>{fileIcon(name)}<Text>{name}</Text></Space>
      ),
    },
    { title: 'Size', dataIndex: 'fileSize', key: 'fileSize', width: 100, render: formatFileSize },
    { title: 'Status', dataIndex: 'status', key: 'status', width: 100, render: statusTag },
    {
      title: 'Uploaded',
      dataIndex: 'uploadedAt',
      key: 'uploadedAt',
      width: 180,
      render: (d: string) => d ? new Date(d).toLocaleString() : '—',
    },
    {
      title: '',
      key: 'actions',
      width: 60,
      render: (_: unknown, record: RAGDocument) => (
        <Tooltip title="Delete">
          <Button
            type="text"
            danger
            size="small"
            icon={<DeleteOutlined />}
            onClick={() => handleDelete([record.docKey])}
          />
        </Tooltip>
      ),
    },
  ];

  // ══════════════════════════════════════════════════════════════════════
  // TAB 1 — Documents
  // ══════════════════════════════════════════════════════════════════════
  const documentsTab = (
    <>
      {/* Upload section */}
      <Card size="small" style={{ marginBottom: 16, background: token.colorBgContainer }}>
        <Row gutter={16} align="middle">
          <Col flex="auto">
            <Upload.Dragger
              multiple
              fileList={fileList}
              beforeUpload={() => false}
              onChange={({ fileList: fl }) => setFileList(fl)}
              accept=".pdf,.doc,.docx,.txt,.md,.csv,.xls,.xlsx,.png,.jpg,.jpeg,.webp"
              style={{ padding: '8px 16px' }}
            >
              <p className="ant-upload-drag-icon">
                <CloudUploadOutlined style={{ fontSize: 28, color: token.colorPrimary }} />
              </p>
              <p className="ant-upload-text" style={{ fontSize: 14 }}>
                Drop files here or click to select
              </p>
              <p className="ant-upload-hint" style={{ fontSize: 12 }}>
                PDF, Word, Excel, images, text — any document type
              </p>
            </Upload.Dragger>
          </Col>
          <Col>
            <Space direction="vertical">
              <Button
                type="primary"
                icon={<UploadOutlined />}
                loading={uploading}
                disabled={!fileList.length}
                onClick={handleUpload}
              >
                Upload {fileList.length ? `(${fileList.length})` : ''}
              </Button>
              {uploading && <Progress percent={uploadProgress} size="small" style={{ width: 120 }} />}
            </Space>
          </Col>
        </Row>
      </Card>

      {/* Actions bar */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col flex="auto">
          <Space>
            <Button
              icon={<ThunderboltOutlined />}
              type="primary"
              ghost
              loading={indexing}
              disabled={!documents.length}
              onClick={handleIndex}
            >
              Build Index
            </Button>
            <Button
              icon={<ReloadOutlined />}
              onClick={() => { fetchDocs(pid); fetchIndexStatus(pid); }}
            >
              Refresh
            </Button>
            {selectedDocs.length > 0 && (
              <Button danger icon={<DeleteOutlined />} onClick={() => handleDelete(selectedDocs)}>
                Delete Selected ({selectedDocs.length})
              </Button>
            )}
          </Space>
        </Col>
      </Row>

      {/* Index status */}
      {indexStatus && indexStatus.status !== 'none' && (
        <Card size="small" style={{ marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {indexStatus.status === 'indexing'
              ? <SyncOutlined spin style={{ color: token.colorPrimary, fontSize: 18 }} />
              : indexStatus.status === 'ready'
                ? <CheckCircleOutlined style={{ color: token.colorSuccess, fontSize: 18 }} />
                : <ExclamationCircleOutlined style={{ color: token.colorError, fontSize: 18 }} />}
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <Text strong style={{ fontSize: 13 }}>
                  {indexStatus.status === 'indexing' ? 'Building Index...' : indexStatus.status === 'ready' ? 'Index Ready' : 'Index Error'}
                </Text>
                <Text type="secondary" style={{ fontSize: 12 }}>{indexStatus.progress ?? 0}%</Text>
              </div>
              <Progress
                percent={indexStatus.progress ?? 0}
                showInfo={false}
                strokeColor={{ from: token.colorPrimary, to: token.colorSuccess }}
                size="small"
                status={indexStatus.status === 'indexing' ? 'active' : indexStatus.status === 'ready' ? 'success' : 'exception'}
              />
              {indexStatus.message && (
                <Text type="secondary" style={{ fontSize: 12, marginTop: 4, display: 'block' }}>
                  {indexStatus.message}
                </Text>
              )}
              {indexStatus.status === 'ready' && (
                <Text type="secondary" style={{ fontSize: 12, marginTop: 4, display: 'block' }}>
                  {indexStatus.docCount || 0} document(s), {indexStatus.chunkCount || 0} chunks
                  {indexStatus.lastIndexedAt ? ` - ${new Date(indexStatus.lastIndexedAt).toLocaleString()}` : ''}
                </Text>
              )}
            </div>
          </div>
        </Card>
      )}

      {/* Document table */}
      <Card
        size="small"
        title={<Text strong>Documents ({documents.length})</Text>}
      >
        <Table
          dataSource={documents}
          columns={columns}
          rowKey="docKey"
          size="small"
          loading={loading}
          pagination={{ pageSize: 20, hideOnSinglePage: true }}
          rowSelection={{
            selectedRowKeys: selectedDocs,
            onChange: (keys) => setSelectedDocs(keys as string[]),
          }}
          locale={{ emptyText: <Empty description="No documents uploaded yet" /> }}
        />
      </Card>
    </>
  );

  // ══════════════════════════════════════════════════════════════════════
  // TAB 2 — Retrieval (Chat Q&A)
  // ══════════════════════════════════════════════════════════════════════
  const isReady = indexStatus?.status === 'ready';

  const retrievalTab = (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 240px)', minHeight: 400 }}>
      {/* Status bar */}
      <div style={{ marginBottom: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Space>
            {indexStatusBadge(indexStatus?.status || 'none')}
            {indexStatus?.docCount != null && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                {indexStatus.docCount} docs · {indexStatus.chunkCount || 0} chunks indexed
              </Text>
            )}
          </Space>
          {chatHistory.length > 0 && (
            <Button size="small" icon={<ClearOutlined />} onClick={clearChat}>
              Clear Chat
          </Button>
        )}
        </div>
        {indexStatus?.status === 'indexing' && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
              <Text type="secondary" style={{ fontSize: 11 }}>
                <SyncOutlined spin /> {indexStatus.message || 'Building index…'}
              </Text>
              <Text type="secondary" style={{ fontSize: 11 }}>{indexStatus.progress ?? 0}%</Text>
            </div>
            <Progress
              percent={indexStatus.progress ?? 0}
              showInfo={false}
              strokeColor={{ from: token.colorPrimary, to: token.colorSuccess }}
              size="small"
              status="active"
            />
          </div>
        )}
      </div>

      {/* Chat messages area */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '16px 8px',
          background: token.colorBgLayout,
          borderRadius: 12,
          border: `1px solid ${token.colorBorderSecondary}`,
          marginBottom: 12,
        }}
      >
        {chatHistory.length === 0 && !querying && (
          <div style={{ textAlign: 'center', padding: '60px 20px' }}>
            <RobotOutlined style={{ fontSize: 48, color: token.colorTextQuaternary, marginBottom: 16 }} />
            <Title level={5} type="secondary" style={{ marginBottom: 8 }}>
              Ask anything about your documents
            </Title>
            <Text type="secondary" style={{ fontSize: 13 }}>
              {isReady
                ? 'Type a question below to search and get AI-synthesized answers from your ingested documents.'
                : 'Upload documents and build the index first, then come here to ask questions.'}
            </Text>
          </div>
        )}

        {chatHistory.map(msg => (
          <ChatBubble key={msg.id} msg={msg} token={token} />
        ))}

        {querying && (
          <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', marginBottom: 16 }}>
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: '50%',
                background: token.colorPrimary,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              <RobotOutlined style={{ color: '#fff', fontSize: 16 }} />
            </div>
            <div
              style={{
                padding: '12px 16px',
                borderRadius: '16px 16px 16px 4px',
                background: token.colorBgElevated,
                boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
              }}
            >
              <Space>
                <Spin size="small" />
                <Text type="secondary">Searching documents and generating answer…</Text>
              </Space>
            </div>
          </div>
        )}

        <div ref={chatEndRef} />
      </div>

      {/* Chat input area */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
        <TextArea
          value={queryText}
          onChange={e => setQueryText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            isReady
              ? 'Ask a question about your documents… (Enter to send, Shift+Enter for new line)'
              : 'Build the index first to enable querying'
          }
          disabled={!isReady || querying}
          autoSize={{ minRows: 1, maxRows: 4 }}
          style={{ flex: 1, borderRadius: 12, padding: '10px 14px', fontSize: 14 }}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={handleSend}
          disabled={!isReady || querying || !queryText.trim()}
          loading={querying}
          style={{
            height: 42,
            width: 42,
            borderRadius: 12,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        />
      </div>
    </div>
  );

  // ══════════════════════════════════════════════════════════════════════
  // Layout
  // ══════════════════════════════════════════════════════════════════════
  return (
    <div style={{ padding: 24, maxWidth: 1200, margin: '0 auto' }}>
      <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
        <Col>
          <Title level={3} style={{ margin: 0 }}>
            <DatabaseOutlined style={{ marginRight: 8 }} />
            Knowledge Base
          </Title>
        </Col>
        <Col>
          <Space>
            {indexStatusBadge(indexStatus?.status || 'none')}
            {indexStatus?.docCount != null && (
              <Text type="secondary">{indexStatus.docCount} docs / {indexStatus.chunkCount || 0} chunks</Text>
            )}
          </Space>
        </Col>
      </Row>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'docs',
            label: (
              <Space>
                <DatabaseOutlined />
                Documents
              </Space>
            ),
            children: documentsTab,
          },
          {
            key: 'retrieval',
            label: (
              <Space>
                <SearchOutlined />
                Retrieval
              </Space>
            ),
            children: retrievalTab,
          },
        ]}
      />
    </div>
  );
};

export default RAGDocuments;
