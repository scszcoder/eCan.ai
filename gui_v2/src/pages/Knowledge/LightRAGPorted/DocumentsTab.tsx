import React, { useState } from 'react';
import { theme } from 'antd';
import { useTranslation } from 'react-i18next';
import { lightragIpc } from '@/services/ipc/lightrag';
import { ScanOutlined, UnorderedListOutlined, ClearOutlined, FolderOpenOutlined, UploadOutlined } from '@ant-design/icons';
import { useTheme } from '@/contexts/ThemeContext';

const DocumentsTab: React.FC = () => {
  const [files, setFiles] = useState<FileList | null>(null);
  const [dirPath, setDirPath] = useState('');
  const [log, setLog] = useState<string>('');
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const { theme: currentTheme } = useTheme();
  const isDark = currentTheme === 'dark' || (currentTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);

  const appendLog = (line: string) => setLog(prev => prev ? prev + '\n' + line : line);

  const handleFilesChange: React.ChangeEventHandler<HTMLInputElement> = (e) => {
    setFiles(e.target.files);
  };

  const handleIngestFiles = async () => {
    if (!files || files.length === 0) {
      appendLog(t('pages.knowledge.documents.noFilesSelected'));
      return;
    }
    const paths: string[] = [];
    for (let i = 0; i < files.length; i++) {
      paths.push(files[i].name);
    }
    try {
      const res = await lightragIpc.ingestFiles({ paths });
      appendLog(t('pages.knowledge.documents.ingestSuccess') + ': ' + JSON.stringify(res));
    } catch (e: any) {
      appendLog(t('pages.knowledge.documents.ingestError') + ': ' + (e?.message || String(e)));
    }
  };

  const handleIngestDir = async () => {
    try {
      const res = await lightragIpc.ingestDirectory({ dirPath });
      appendLog(t('pages.knowledge.documents.ingestSuccess') + ': ' + JSON.stringify(res));
    } catch (e: any) {
      appendLog(t('pages.knowledge.documents.ingestError') + ': ' + (e?.message || String(e)));
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
          <button className="ec-btn" title={t('pages.knowledge.documents.scan')}>
            <ScanOutlined /> {t('pages.knowledge.documents.scan')}
          </button>
          <button className="ec-btn" title={t('pages.knowledge.documents.status')}>
            <UnorderedListOutlined /> {t('pages.knowledge.documents.status')}
          </button>
          <button className="ec-btn" title={t('pages.knowledge.documents.clear')}>
            <ClearOutlined /> {t('pages.knowledge.documents.clear')}
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
              <input 
                type="file" 
                multiple 
                onChange={handleFilesChange}
                id="file-upload"
                className="ec-file-input"
              />
            </div>
            <button className="ec-btn ec-btn-primary" onClick={handleIngestFiles} style={{ marginTop: 26 }}>
              <UploadOutlined /> {t('pages.knowledge.documents.ingest')}
            </button>
          </div>
          <div style={{ height: 1, background: token.colorBorderSecondary }} />
          <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end' }}>
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
              <label style={{ fontSize: 13, fontWeight: 600, color: token.colorTextSecondary }}>{t('pages.knowledge.documents.importDirectory')}</label>
              <input 
                className="ec-input" 
                placeholder={t('pages.knowledge.documents.enterDirectoryPath')}
                value={dirPath} 
                onChange={e => setDirPath(e.target.value)}
              />
            </div>
            <button className="ec-btn ec-btn-primary" onClick={handleIngestDir}>
              <FolderOpenOutlined /> {t('pages.knowledge.documents.ingest')}
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
            <span><strong>{t('pages.knowledge.documents.all')}:</strong> 0</span>
            <span style={{ color: token.colorSuccess }}><strong>{t('pages.knowledge.documents.completed')}:</strong> 0</span>
            <span style={{ color: token.colorWarning }}><strong>{t('pages.knowledge.documents.processing')}:</strong> 0</span>
            <span style={{ color: token.colorTextTertiary }}><strong>{t('pages.knowledge.documents.pending')}:</strong> 0</span>
            <span style={{ color: token.colorError }}><strong>{t('pages.knowledge.documents.failed')}:</strong> 0</span>
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
            gridTemplateColumns: '1fr 100px', 
            gap: 8, 
            padding: '12px 16px',
            background: isDark ? token.colorBgTextHover : token.colorBgLayout,
            borderBottom: `1px solid ${token.colorBorder}`,
            fontWeight: 600,
            fontSize: 13,
            color: token.colorText
          }}>
            <div>{t('pages.knowledge.documents.fileName')}</div>
            <div style={{ textAlign: 'center' }}>{t('pages.knowledge.documents.actions')}</div>
          </div>
          {/* Empty state */}
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
