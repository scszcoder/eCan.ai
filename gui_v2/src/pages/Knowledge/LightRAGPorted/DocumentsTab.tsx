import React, { useState } from 'react';
import { lightragIpc } from '@/services/ipc/lightrag';

const DocumentsTab: React.FC = () => {
  const [files, setFiles] = useState<FileList | null>(null);
  const [dirPath, setDirPath] = useState('');
  const [log, setLog] = useState<string>('');

  const appendLog = (line: string) => setLog(prev => prev ? prev + '\n' + line : line);

  const handleFilesChange: React.ChangeEventHandler<HTMLInputElement> = (e) => {
    setFiles(e.target.files);
  };

  const handleIngestFiles = async () => {
    if (!files || files.length === 0) {
      appendLog('No files selected');
      return;
    }
    const paths: string[] = [];
    // Best effort: in browser context we may not have disk paths. Leave placeholder.
    for (let i = 0; i < files.length; i++) {
      paths.push(files[i].name);
    }
    try {
      const res = await lightragIpc.ingestFiles({ paths });
      appendLog('ingestFiles: ' + JSON.stringify(res));
    } catch (e: any) {
      appendLog('ingestFiles error: ' + (e?.message || String(e)));
    }
  };

  const handleIngestDir = async () => {
    try {
      const res = await lightragIpc.ingestDirectory({ dirPath });
      appendLog('ingestDirectory: ' + JSON.stringify(res));
    } catch (e: any) {
      appendLog('ingestDirectory error: ' + (e?.message || String(e)));
    }
  };

  return (
    <div style={{ padding: 16 }} data-ec-scope="lightrag-ported">
      {/* Document Management header and actions */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <h3 style={{ margin: 0 }}>Document Management</h3>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="ec-btn" title="Scan">Scan</button>
          <button className="ec-btn" title="Pipeline Status">Pipeline Status</button>
          <button className="ec-btn" title="Clear">Clear</button>
        </div>
      </div>

      {/* Existing ingest helpers */}
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12 }}>
        <input type="file" multiple onChange={handleFilesChange} />
        <button className="ec-btn" onClick={handleIngestFiles}>Ingest Files</button>
      </div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 16 }}>
        <input className="ec-input" placeholder="Directory path" value={dirPath} onChange={e => setDirPath(e.target.value)} style={{ flex: 1 }} />
        <button className="ec-btn" onClick={handleIngestDir}>Ingest Directory</button>
      </div>

      {/* Uploaded Documents section */}
      <div style={{ marginTop: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <h4 style={{ margin: 0 }}>Uploaded Documents</h4>
          <div style={{ display: 'flex', gap: 12, fontSize: 12 }}>
            <span>All (0)</span>
            <span>Completed (0)</span>
            <span>Processing (0)</span>
            <span>Pending (0)</span>
            <span>Failed (0)</span>
          </div>
        </div>

        {/* Table header */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 80px', gap: 8, padding: '8px 12px', border: '1px solid var(--ant-color-border, #d9d9d9)', borderRadius: 8, background: 'var(--ant-color-bg-container, #fff)' }}>
          <div style={{ fontWeight: 600 }}>File Name</div>
          <div style={{ fontWeight: 600, textAlign: 'right' }}>Show</div>
          {/* Empty state row */}
          <div style={{ gridColumn: '1 / span 2', padding: '24px 0', textAlign: 'center', color: 'var(--ant-color-text-tertiary, #888)' }}>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>No Documents</div>
            <div>There are no uploaded documents yet.</div>
          </div>
        </div>
      </div>

      {/* Log console */}
      <pre style={{ background: 'var(--ant-color-bg-container, #111)', color: 'var(--ant-color-text, #ddd)', padding: 12, borderRadius: 8, minHeight: 120, marginTop: 16 }}>{log}</pre>

      {/* Scoped styles */}
      <style>{`
        [data-ec-scope="lightrag-ported"] .ec-btn {
          background: #ffffff !important;
          color: #111111 !important;
          border: 1px solid #d9d9d9 !important;
          border-radius: 6px;
          padding: 6px 12px;
          cursor: pointer;
        }
        [data-ec-scope="lightrag-ported"] .ec-btn:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }
      `}</style>
    </div>
  );
};

export default DocumentsTab;
