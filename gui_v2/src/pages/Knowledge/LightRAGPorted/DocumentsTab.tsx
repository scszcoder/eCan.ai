import React, { useState } from 'react';
import { theme } from 'antd';
import { useTranslation } from 'react-i18next';
import { lightragIpc } from '@/services/ipc/lightrag';
import { get_ipc_api } from '@/services/ipc_api';
import { ScanOutlined, UnorderedListOutlined, ClearOutlined, FolderOpenOutlined, UploadOutlined } from '@ant-design/icons';
import { useTheme } from '@/contexts/ThemeContext';

interface Document {
  file_path: string;
  status: string;
  content_length?: number;
  created_at?: string;
  updated_at?: string;
}

const DocumentsTab: React.FC = () => {
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [dirPath, setDirPath] = useState('');
  const [log, setLog] = useState<string>('');
  const [documents, setDocuments] = useState<Document[]>([]);
  const [statusCounts, setStatusCounts] = useState({ all: 0, PROCESSED: 0, PROCESSING: 0, PENDING: 0, FAILED: 0 });
  const [loading, setLoading] = useState(false);
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const { theme: currentTheme } = useTheme();
  const isDark = currentTheme === 'dark' || (currentTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);

  const appendLog = (line: string) => setLog(prev => prev ? prev + '\n' + line : line);

  // Load documents on mount
  React.useEffect(() => {
    loadDocuments();
  }, []);

  const handleSelectFiles = async () => {
    try {
      const api: any = get_ipc_api();
      const result: any = await api.fs?.selectFiles?.({ multiple: true });
      if (result && result.paths && result.paths.length > 0) {
        setSelectedFiles(result.paths);
        appendLog(`Selected ${result.paths.length} file(s)`);
      }
    } catch (e: any) {
      appendLog('Error selecting files: ' + (e?.message || String(e)));
    }
  };

  const handleSelectDirectory = async () => {
    try {
      const api: any = get_ipc_api();
      const result: any = await api.fs?.selectDirectory?.({});
      if (result && result.path) {
        setDirPath(result.path);
      }
    } catch (e: any) {
      appendLog('Error selecting directory: ' + (e?.message || String(e)));
    }
  };

  const handleIngestFiles = async () => {
    if (!selectedFiles || selectedFiles.length === 0) {
      appendLog(t('pages.knowledge.documents.noFilesSelected'));
      return;
    }
    try {
      appendLog(`Ingesting ${selectedFiles.length} file(s)...`);
      const res = await lightragIpc.ingestFiles({ paths: selectedFiles });
      appendLog(t('pages.knowledge.documents.ingestSuccess') + ': ' + JSON.stringify(res));
      // Reload documents after ingestion
      setTimeout(() => loadDocuments(), 2000);
    } catch (e: any) {
      appendLog(t('pages.knowledge.documents.ingestError') + ': ' + (e?.message || String(e)));
    }
  };

  const handleIngestDir = async () => {
    if (!dirPath) {
      appendLog('Please select a directory first');
      return;
    }
    try {
      appendLog(`Ingesting directory: ${dirPath}...`);
      const res = await lightragIpc.ingestDirectory({ dirPath });
      appendLog(t('pages.knowledge.documents.ingestSuccess') + ': ' + JSON.stringify(res));
      // Reload documents after ingestion
      setTimeout(() => loadDocuments(), 2000);
    } catch (e: any) {
      appendLog(t('pages.knowledge.documents.ingestError') + ': ' + (e?.message || String(e)));
    }
  };

  const loadDocuments = async () => {
    try {
      setLoading(true);
      const res = await lightragIpc.listDocuments();
      if (res && res.data && res.data.statuses) {
        // Flatten all documents from different statuses
        const allDocs: Document[] = [];
        const counts = { all: 0, PROCESSED: 0, PROCESSING: 0, PENDING: 0, FAILED: 0 };
        
        Object.keys(res.data.statuses).forEach((status: string) => {
          const docs = res.data.statuses[status] || [];
          docs.forEach((doc: any) => {
            allDocs.push({ ...doc, status });
          });
          counts[status as keyof typeof counts] = docs.length;
          counts.all += docs.length;
        });
        
        setDocuments(allDocs);
        setStatusCounts(counts);
        appendLog(`Loaded ${counts.all} documents`);
      }
    } catch (e: any) {
      appendLog('Error loading documents: ' + (e?.message || String(e)));
    } finally {
      setLoading(false);
    }
  };

  const handleScan = async () => {
    try {
      appendLog('Starting scan for new documents...');
      const res = await lightragIpc.scan();
      appendLog('Scan started: ' + JSON.stringify(res));
      // Reload documents after scan
      setTimeout(() => loadDocuments(), 2000);
    } catch (e: any) {
      appendLog('Error scanning: ' + (e?.message || String(e)));
    }
  };

  const handleRefreshStatus = async () => {
    appendLog('Refreshing document status...');
    await loadDocuments();
  };

  const handleClearCache = async () => {
    if (!confirm('Clear all cache? This will remove processed data from the knowledge base.')) return;
    
    try {
      appendLog('Clearing cache...');
      await lightragIpc.clearCache();
      appendLog('Cache cleared successfully');
      // Reload documents after clearing cache
      await loadDocuments();
    } catch (e: any) {
      appendLog('Error clearing cache: ' + (e?.message || String(e)));
    }
  };
  
  const handleClearLog = () => {
    setLog('');
  };

  const handleDeleteDocument = async (filePath: string) => {
    if (!confirm(`Delete document: ${filePath}?`)) return;
    
    try {
      appendLog(`Deleting document: ${filePath}...`);
      await lightragIpc.deleteDocument({ filePath });
      appendLog('Document deleted successfully');
      // Reload documents
      await loadDocuments();
    } catch (e: any) {
      appendLog('Error deleting document: ' + (e?.message || String(e)));
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'PROCESSED': return token.colorSuccess;
      case 'PROCESSING': return token.colorWarning;
      case 'PENDING': return token.colorTextTertiary;
      case 'FAILED': return token.colorError;
      default: return token.colorText;
    }
  };

  return (
    <div style={{ 
      height: '100%', 
      overflow: 'auto'
    }}>
      <div style={{ 
        padding: '32px', 
        minHeight: '100%',
        display: 'flex', 
        flexDirection: 'column', 
        gap: 24,
        background: token.colorBgLayout
      }} data-ec-scope="lightrag-ported">
      {/* Document Management header and actions */}
      <div style={{ 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'space-between',
        padding: '16px 0',
        marginBottom: 8
      }}>
        <div>
          <h3 style={{ 
            margin: 0, 
            fontSize: 18, 
            fontWeight: 600, 
            color: token.colorText,
            lineHeight: 1.2
          }}>
            {t('pages.knowledge.documents.title')}
          </h3>
          <p style={{ 
            margin: '4px 0 0 0', 
            fontSize: 13, 
            color: token.colorTextSecondary 
          }}>
            {t('pages.knowledge.documents.subtitle')}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="ec-btn" onClick={handleScan} title={t('pages.knowledge.documents.scan')}>
            <ScanOutlined /> {t('pages.knowledge.documents.scan')}
          </button>
          <button className="ec-btn" onClick={handleRefreshStatus} title={t('pages.knowledge.documents.status')}>
            <UnorderedListOutlined /> {t('pages.knowledge.documents.status')}
          </button>
          <button className="ec-btn" onClick={handleClearCache} title="Clear Cache">
            <ClearOutlined /> Clear Cache
          </button>
          <button className="ec-btn" onClick={handleClearLog} title="Clear Log">
            Clear Log
          </button>
        </div>
      </div>

      {/* Ingest section */}
      <div style={{
        background: token.colorBgContainer,
        borderRadius: 16,
        border: `1px solid ${token.colorBorder}`,
        overflow: 'hidden',
        boxShadow: isDark ? '0 4px 16px rgba(0, 0, 0, 0.15)' : '0 4px 16px rgba(0, 0, 0, 0.06)'
      }}>
        <div style={{ padding: '20px 24px', borderBottom: `1px solid ${token.colorBorderSecondary}` }}>
          <h4 style={{ margin: 0, fontSize: 15, fontWeight: 600, color: token.colorText }}>{t('pages.knowledge.documents.importDocuments')}</h4>
        </div>
        <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
              <label style={{ fontSize: 13, fontWeight: 600, color: token.colorTextSecondary }}>{t('pages.knowledge.documents.uploadFiles')}</label>
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="ec-btn" onClick={handleSelectFiles} style={{ flex: 1 }}>
                  <FolderOpenOutlined /> Select Files ({selectedFiles.length} selected)
                </button>
                <button className="ec-btn ec-btn-primary" onClick={handleIngestFiles} disabled={selectedFiles.length === 0}>
                  <UploadOutlined /> {t('pages.knowledge.documents.ingest')}
                </button>
              </div>
            </div>
          </div>
          <div style={{ height: 1, background: token.colorBorderSecondary }} />
          <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end' }}>
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
              <label style={{ fontSize: 13, fontWeight: 600, color: token.colorTextSecondary }}>{t('pages.knowledge.documents.importDirectory')}</label>
              <div style={{ display: 'flex', gap: 8 }}>
                <input 
                  className="ec-input" 
                  placeholder={t('pages.knowledge.documents.enterDirectoryPath')}
                  value={dirPath} 
                  onChange={e => setDirPath(e.target.value)}
                  style={{ flex: 1 }}
                />
                <button className="ec-btn" onClick={handleSelectDirectory}>
                  <FolderOpenOutlined /> Browse
                </button>
              </div>
            </div>
            <button className="ec-btn ec-btn-primary" onClick={handleIngestDir} disabled={!dirPath}>
              <UploadOutlined /> {t('pages.knowledge.documents.ingest')}
            </button>
          </div>
        </div>
      </div>

      {/* Uploaded Documents section */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <div style={{ 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'space-between', 
          marginBottom: 12,
          paddingBottom: 12,
          borderBottom: `1px solid ${token.colorBorderSecondary}`
        }}>
          <h4 style={{ margin: 0, fontSize: 15, fontWeight: 600, color: token.colorText }}>{t('pages.knowledge.documents.uploadedDocuments')}</h4>
          <div style={{ display: 'flex', gap: 16, fontSize: 12, color: token.colorTextSecondary }}>
            <span><strong>{t('pages.knowledge.documents.all')}:</strong> {statusCounts.all}</span>
            <span style={{ color: token.colorSuccess }}><strong>{t('pages.knowledge.documents.completed')}:</strong> {statusCounts.PROCESSED}</span>
            <span style={{ color: token.colorWarning }}><strong>{t('pages.knowledge.documents.processing')}:</strong> {statusCounts.PROCESSING}</span>
            <span style={{ color: token.colorTextTertiary }}><strong>{t('pages.knowledge.documents.pending')}:</strong> {statusCounts.PENDING}</span>
            <span style={{ color: token.colorError }}><strong>{t('pages.knowledge.documents.failed')}:</strong> {statusCounts.FAILED}</span>
          </div>
        </div>

        {/* Table */}
        <div style={{ 
          flex: 1,
          border: `1px solid ${token.colorBorder}`, 
          borderRadius: 16, 
          background: token.colorBgContainer,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: isDark ? '0 4px 16px rgba(0, 0, 0, 0.15)' : '0 4px 16px rgba(0, 0, 0, 0.06)'
        }}>
          <div style={{ 
            display: 'grid', 
            gridTemplateColumns: '1fr 120px 120px 100px', 
            gap: 8, 
            padding: '12px 16px',
            background: isDark ? token.colorBgTextHover : token.colorBgLayout,
            borderBottom: `1px solid ${token.colorBorder}`,
            fontWeight: 600,
            fontSize: 13,
            color: token.colorText
          }}>
            <div>{t('pages.knowledge.documents.fileName')}</div>
            <div style={{ textAlign: 'center' }}>Status</div>
            <div style={{ textAlign: 'center' }}>Updated</div>
            <div style={{ textAlign: 'center' }}>{t('pages.knowledge.documents.actions')}</div>
          </div>
          
          {loading ? (
            <div style={{ 
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '48px 24px',
              color: token.colorTextTertiary
            }}>
              Loading...
            </div>
          ) : documents.length === 0 ? (
            <div style={{ 
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '48px 24px',
              color: token.colorTextTertiary,
              flexDirection: 'column',
              gap: 8
            }}>
              <div style={{ fontSize: 48, opacity: 0.3 }}>📄</div>
              <div style={{ fontWeight: 600, fontSize: 15 }}>{t('pages.knowledge.documents.noDocuments')}</div>
              <div style={{ fontSize: 13 }}>{t('pages.knowledge.documents.noDocumentsDesc')}</div>
            </div>
          ) : (
            <div style={{ flex: 1, overflow: 'auto' }}>
              {documents.map((doc, idx) => (
                <div key={idx} style={{ 
                  display: 'grid', 
                  gridTemplateColumns: '1fr 120px 120px 100px', 
                  gap: 8, 
                  padding: '12px 16px',
                  borderBottom: `1px solid ${token.colorBorderSecondary}`,
                  fontSize: 13,
                  alignItems: 'center',
                  transition: 'background 0.2s'
                }}>
                  <div style={{ 
                    overflow: 'hidden', 
                    textOverflow: 'ellipsis', 
                    whiteSpace: 'nowrap',
                    color: token.colorText
                  }} title={doc.file_path}>
                    {doc.file_path}
                  </div>
                  <div style={{ 
                    textAlign: 'center',
                    color: getStatusColor(doc.status),
                    fontWeight: 600
                  }}>
                    {doc.status}
                  </div>
                  <div style={{ 
                    textAlign: 'center',
                    color: token.colorTextSecondary,
                    fontSize: 12
                  }}>
                    {doc.updated_at ? new Date(doc.updated_at).toLocaleString() : '-'}
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <button 
                      className="ec-btn-small"
                      onClick={() => handleDeleteDocument(doc.file_path)}
                      style={{
                        padding: '4px 12px',
                        fontSize: 12,
                        background: token.colorErrorBg,
                        color: token.colorError,
                        border: `1px solid ${token.colorErrorBorder}`,
                        borderRadius: 6,
                        cursor: 'pointer',
                        transition: 'all 0.2s'
                      }}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Log console */}
      <div style={{ 
        background: isDark ? token.colorBgElevated : token.colorBgContainer, 
        color: token.colorText, 
        padding: 20, 
        borderRadius: 16, 
        minHeight: 140,
        maxHeight: 220,
        overflow: 'auto',
        fontFamily: 'Monaco, Consolas, "Courier New", monospace',
        fontSize: 13,
        lineHeight: 1.8,
        border: `1px solid ${token.colorBorder}`,
        boxShadow: isDark ? 'inset 0 2px 8px rgba(0, 0, 0, 0.2)' : 'inset 0 2px 8px rgba(0, 0, 0, 0.05)'
      }}>
        {log || <span style={{ opacity: 0.5, color: token.colorTextTertiary }}>{t('pages.knowledge.documents.consoleOutput')}</span>}
      </div>

      {/* Scoped styles */}
      <style>{`
        [data-ec-scope="lightrag-ported"] .ec-input {
          background: ${token.colorBgContainer};
          color: ${token.colorText};
          border: 1px solid ${token.colorBorder};
          border-radius: 10px;
          padding: 10px 14px;
          font-size: 14px;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        [data-ec-scope="lightrag-ported"] .ec-input:focus {
          outline: none;
          border-color: ${token.colorPrimary};
          box-shadow: 0 0 0 2px ${token.colorPrimaryBg};
        }
        [data-ec-scope="lightrag-ported"] .ec-btn {
          background: ${token.colorBgContainer};
          color: ${token.colorText};
          border: 1px solid ${token.colorBorder};
          border-radius: 10px;
          padding: 10px 18px;
          cursor: pointer;
          font-size: 14px;
          display: inline-flex;
          align-items: center;
          gap: 8px;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          font-weight: 500;
          box-shadow: ${isDark ? '0 2px 8px rgba(0, 0, 0, 0.15)' : '0 2px 8px rgba(0, 0, 0, 0.05)'};
        }
        [data-ec-scope="lightrag-ported"] .ec-btn:hover {
          border-color: ${token.colorPrimary};
          color: ${token.colorPrimary};
          transform: translateY(-2px);
          box-shadow: ${isDark ? '0 4px 12px rgba(24, 144, 255, 0.3)' : '0 4px 12px rgba(24, 144, 255, 0.2)'};
        }
        [data-ec-scope="lightrag-ported"] .ec-btn-primary {
          background: ${token.colorPrimary};
          color: #ffffff;
          border-color: ${token.colorPrimary};
        }
        [data-ec-scope="lightrag-ported"] .ec-btn-primary:hover {
          background: ${token.colorPrimaryHover};
          border-color: ${token.colorPrimaryHover};
          color: #ffffff;
          transform: translateY(-2px);
          box-shadow: 0 6px 16px rgba(24, 144, 255, 0.4);
        }
        [data-ec-scope="lightrag-ported"] .ec-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        [data-ec-scope="lightrag-ported"] .ec-file-input {
          padding: 12px;
          border: 2px dashed ${token.colorBorder};
          border-radius: 10px;
          background: ${isDark ? token.colorBgElevated : token.colorBgLayout};
          color: ${token.colorText};
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          cursor: pointer;
          font-size: 13px;
        }
        [data-ec-scope="lightrag-ported"] .ec-file-input:hover {
          border-color: ${token.colorPrimary};
          background: ${token.colorPrimaryBg};
        }
        [data-ec-scope="lightrag-ported"] .ec-file-input::file-selector-button {
          padding: 6px 12px;
          border: 1px solid ${token.colorBorder};
          border-radius: 6px;
          background: ${token.colorBgContainer};
          color: ${token.colorText};
          cursor: pointer;
          margin-right: 12px;
          font-size: 13px;
          font-weight: 500;
          transition: all 0.2s;
        }
        [data-ec-scope="lightrag-ported"] .ec-file-input::file-selector-button:hover {
          background: ${token.colorPrimary};
          color: #ffffff;
          border-color: ${token.colorPrimary};
        }
      `}</style>
      </div>
    </div>
  );
};

export default DocumentsTab;
