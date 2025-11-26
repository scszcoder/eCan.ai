import { theme, Pagination, Select, Modal, App } from 'antd';
import { useTranslation } from 'react-i18next';
import { get_ipc_api } from '@/services/ipc_api';
import { ScanOutlined, UnorderedListOutlined, ClearOutlined, FolderOpenOutlined, UploadOutlined } from '@ant-design/icons';
import { useTheme } from '@/contexts/ThemeContext';
import React, { useState } from 'react';

interface Document {
  id: string;
  file_path: string;
  status: string;
  content_length?: number;
  created_at?: string;
  updated_at?: string;
}

const DocumentsTab: React.FC = () => {
  const { message } = App.useApp();
  const [modal, contextHolder] = Modal.useModal();
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [dirPath, setDirPath] = useState('');
  const [log, setLog] = useState<string>('');
  const [documents, setDocuments] = useState<Document[]>([]);
  const [statusCounts, setStatusCounts] = useState({ all: 0, PROCESSED: 0, PROCESSING: 0, PENDING: 0, FAILED: 0 });
  const [loading, setLoading] = useState(false);
  
  // Pagination state
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [totalDocs, setTotalDocs] = useState(0);
  const [statusFilter, setStatusFilter] = useState<string | null>(null);

  const { t } = useTranslation();
  const { token } = theme.useToken();
  const { theme: currentTheme } = useTheme();
  const isDark = currentTheme === 'dark' || (currentTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);

  const appendLog = (line: string) => setLog(prev => prev ? prev + '\n' + line : line);

  // Load documents on mount
  React.useEffect(() => {
    loadDocuments();
    loadStatusCounts();
  }, [currentPage, pageSize, statusFilter]);

  const handleSelectFiles = async () => {
    try {
      // 5 minutes timeout for user interaction
      const response = await get_ipc_api().executeRequest<any>('fs.selectFiles', { multiple: true }, 300000);
      if (response.success && response.data) {
          const result = response.data;
          if (result && result.paths && result.paths.length > 0) {
            setSelectedFiles(result.paths);
            appendLog(t('pages.knowledge.documents.selectFilesWithCount', { count: result.paths.length }));
          }
      }
    } catch (e: any) {
      appendLog(t('pages.knowledge.documents.errorSelectingFiles') + (e?.message || String(e)));
    }
  };

  const handleSelectDirectory = async () => {
    try {
      // 5 minutes timeout for user interaction
      const response = await get_ipc_api().executeRequest<any>('fs.selectDirectory', {}, 300000);
      if (response.success && response.data) {
          const result = response.data;
          if (result && result.path) {
            setDirPath(result.path);
          }
      }
    } catch (e: any) {
      appendLog(t('pages.knowledge.documents.errorSelectingDirectory') + (e?.message || String(e)));
    }
  };

  const handleIngestFiles = async () => {
    if (!selectedFiles || selectedFiles.length === 0) {
      appendLog(t('pages.knowledge.documents.noFilesSelected'));
      return;
    }
    try {
      appendLog(`Ingesting ${selectedFiles.length} file(s)...`);
      const response = await get_ipc_api().lightragApi.ingestFiles({ paths: selectedFiles });
      if (response.success && response.data) {
          const res = response.data as any; // The inner result from backend
          appendLog(t('pages.knowledge.documents.ingestSuccess') + ': ' + JSON.stringify(res));
          // Reload documents after ingestion
          setTimeout(() => {
            loadDocuments();
            loadStatusCounts();
          }, 2000);
      } else {
          throw new Error(response.error?.message || 'Unknown error');
      }
    } catch (e: any) {
      appendLog(t('pages.knowledge.documents.ingestError') + ': ' + (e?.message || String(e)));
    }
  };

  const handleIngestDir = async () => {
    if (!dirPath) {
      appendLog(t('pages.knowledge.documents.selectDirectoryFirst'));
      return;
    }
    try {
      appendLog(`Ingesting directory: ${dirPath}...`);
      const response = await get_ipc_api().lightragApi.ingestDirectory({ dirPath });
      if (response.success && response.data) {
          const res = response.data as any;
          const summary = res && res.data ? res.data : res;
          if (summary) {
            const total = summary.total_files ?? summary.totalFiles ?? 0;
            const successCount = summary.success_count ?? summary.successCount ?? 0;
            const failureCount = summary.failure_count ?? summary.failureCount ?? 0;
            const statusText = summary.status || 'unknown';

            appendLog(
              `${t('pages.knowledge.documents.ingestSuccess')}: ` +
              `status=${statusText}, total=${total}, success=${successCount}, failed=${failureCount}`
            );

            if (Array.isArray(summary.files) && summary.files.length > 0) {
              const maxPreview = 5;
              const fileNames = summary.files
                .slice(0, maxPreview)
                .map((f: any) => (f && f.file_path) || '')
                .filter((name: string) => !!name);
              if (fileNames.length > 0) {
                const moreCount = summary.files.length > maxPreview ? `, ... (+${summary.files.length - maxPreview} more)` : '';
                appendLog(`Files: ${fileNames.join(', ')}${moreCount}`);
              }
            }
          } else {
            appendLog(t('pages.knowledge.documents.ingestSuccess') + ': ' + JSON.stringify(res));
          }
          setTimeout(() => {
            loadDocuments();
            loadStatusCounts();
          }, 2000);
      } else {
          throw new Error(response.error?.message || 'Unknown error');
      }
    } catch (e: any) {
      appendLog(t('pages.knowledge.documents.ingestError') + ': ' + (e?.message || String(e)));
    }
  };

  const loadStatusCounts = async () => {
    try {
      const response = await get_ipc_api().lightragApi.getStatusCounts();
      if (response.success && response.data) {
          const res = response.data as any;
          if (res && res.data && res.data.status_counts) {
            const counts = res.data.status_counts;
            
            // Normalize keys to uppercase to handle potential case mismatch (e.g. 'failed' vs 'FAILED')
            const normalizedCounts: Record<string, number> = {};
            Object.keys(counts).forEach(key => {
              normalizedCounts[key.toUpperCase()] = counts[key];
            });

            // Calculate total
            let all = 0;
            Object.values(counts).forEach((c: any) => all += (c || 0));
            
            setStatusCounts({
              all,
              PROCESSED: normalizedCounts.PROCESSED || 0,
              PROCESSING: normalizedCounts.PROCESSING || 0,
              PENDING: normalizedCounts.PENDING || 0,
              FAILED: normalizedCounts.FAILED || 0
            });
          }
      }
    } catch (e) {
      console.error('Error loading status counts:', e);
    }
  };

  const loadDocuments = async () => {
    try {
      setLoading(true);
      
      // Use paginated API
      const response = await get_ipc_api().lightragApi.getDocumentsPaginated({
        page: currentPage,
        page_size: pageSize,
        status_filter: statusFilter === 'ALL' ? null : statusFilter,
        sort_field: 'updated_at',
        sort_direction: 'desc'
      });

      if (response.success && response.data) {
          const res = response.data as any;
          if (res && res.data && res.data.documents) {
            setDocuments(res.data.documents);
            setTotalDocs(res.data.pagination?.total_count || 0);
            appendLog(t('pages.knowledge.documents.loadedDocuments', { count: res.data.documents.length, page: currentPage }));
          } else if (res && res.data && res.data.statuses) {
            // Fallback for older API or if pagination not supported fully
            // Flatten all documents from different statuses
            const allDocs: Document[] = [];
            Object.keys(res.data.statuses).forEach((status: string) => {
              if (statusFilter && statusFilter !== 'ALL' && status !== statusFilter) return;
              const docs = res.data.statuses[status] || [];
              docs.forEach((doc: any) => {
                allDocs.push({ ...doc, status });
              });
            });
            
            // Manual pagination if backend returns all
            const start = (currentPage - 1) * pageSize;
            const end = start + pageSize;
            setDocuments(allDocs.slice(start, end));
            setTotalDocs(allDocs.length);
          }
      } else {
          appendLog('Error loading documents: ' + (response.error?.message || 'Unknown error'));
      }
    } catch (e: any) {
      appendLog('Error loading documents: ' + (e?.message || String(e)));
    } finally {
      setLoading(false);
    }
  };

  const handleScan = async () => {
    try {
      appendLog(t('pages.knowledge.documents.startingScan'));
      
      // Record current failed count before scan
      const previousFailedCount = statusCounts.FAILED;
      
      const response = await get_ipc_api().lightragApi.scan();
      if (response.success && response.data) {
          const res = response.data as any;
          appendLog(t('pages.knowledge.documents.scanStarted') + JSON.stringify(res));
          message.success(t('pages.knowledge.documents.scanStarted') + (res.message || ''));
          
          // Reload documents after scan and start polling for failures
          setTimeout(async () => {
            await loadDocuments();
            await loadStatusCounts();
            
            // Poll for failed documents - check every 3 seconds for up to 120 seconds
            let pollCount = 0;
            const maxPolls = 40; // 40 polls * 3 seconds = 120 seconds max
            let failureDetected = false;
            
            console.log('[DocumentsTab] Starting failure detection polling...');
            appendLog('🔍 Starting failure detection polling (checking every 3s for up to 120s)...');
            
            const pollInterval = setInterval(async () => {
              pollCount++;
              console.log(`[DocumentsTab] Poll #${pollCount}/${maxPolls}`);
              
              // Stop polling after max attempts or if failure detected
              if (pollCount >= maxPolls || failureDetected) {
                console.log(`[DocumentsTab] Stopping polling. Reason: ${failureDetected ? 'failure detected' : 'max polls reached'}`);
                appendLog(`🛑 Stopping failure detection polling (${failureDetected ? 'failure detected' : 'max attempts reached'})`);
                clearInterval(pollInterval);
                return;
              }
              
              try {
                const statusResponse = await get_ipc_api().lightragApi.getStatusCounts();
                if (statusResponse.success && statusResponse.data) {
                  const statusData = statusResponse.data as any;
                  // Try both possible data structures
                  const statusCounts = statusData?.data?.status_counts || statusData?.status_counts || {};
                  // Handle both uppercase and lowercase keys
                  const newFailedCount = statusCounts?.FAILED || statusCounts?.failed || 0;
                  const processingCount = statusCounts?.PROCESSING || statusCounts?.processing || 0;
                  const pendingCount = statusCounts?.PENDING || statusCounts?.pending || 0;
                  
                  console.log(`[DocumentsTab] Poll #${pollCount}: FAILED=${newFailedCount} (was ${previousFailedCount}), PROCESSING=${processingCount}, PENDING=${pendingCount}`);
                  console.log(`[DocumentsTab] Full status counts:`, statusCounts);
                  console.log(`[DocumentsTab] Raw statusData:`, statusData);
                  
                  // Check for failures FIRST (before early stop check)
                  if (newFailedCount > previousFailedCount) {
                    failureDetected = true;
                    clearInterval(pollInterval);
                    
                    const failedDiff = newFailedCount - previousFailedCount;
                    let errorDetails = '';
                    
                    console.log(`[DocumentsTab] Detected ${failedDiff} new failed document(s), fetching details...`);
                    
                    // Fetch failed documents to get error details
                    try {
                      const failedDocsResponse = await get_ipc_api().lightragApi.getDocumentsPaginated({
                        page: 1,
                        page_size: 10,
                        status_filter: 'failed',  // Use lowercase to match backend status format
                        sort_field: 'updated_at',
                        sort_direction: 'desc'
                      });
                      
                      console.log(`[DocumentsTab] getDocumentsPaginated response:`, failedDocsResponse);
                      
                      if (!failedDocsResponse.success) {
                        console.error(`[DocumentsTab] Failed to fetch failed documents:`, failedDocsResponse.error);
                        appendLog(`❌ Failed to fetch failed document details: ${failedDocsResponse.error?.message || 'Unknown error'}`);
                      }
                      
                      if (failedDocsResponse.success && failedDocsResponse.data) {
                        const failedData = failedDocsResponse.data as any;
                        const failedDocs = failedData?.data?.documents || [];
                        
                        console.log(`[DocumentsTab] Failed docs response:`, failedDocsResponse);
                        console.log(`[DocumentsTab] Failed docs count: ${failedDocs.length}`);
                        if (failedDocs.length > 0) {
                          console.log(`[DocumentsTab] First failed doc:`, failedDocs[0]);
                        }
                        
                        // Log details of failed documents
                        if (failedDocs.length > 0) {
                          appendLog(`\n=== Failed Documents Details ===`);
                          failedDocs.slice(0, 3).forEach((doc: any) => {
                            appendLog(`📄 File: ${doc.file_path}`);
                            appendLog(`   Status: ${doc.status}`);
                            appendLog(`   Updated: ${doc.updated_at || 'N/A'}`);
                            // LightRAG saves error in 'error_msg' field (not 'error_message')
                            if (doc.error_msg) {
                              appendLog(`   Error: ${doc.error_msg}`);
                            }
                          });
                          appendLog(`================================\n`);
                          
                          // Build error summary for UI message
                          const firstDoc = failedDocs[0];
                          if (firstDoc.file_path) {
                            errorDetails = `\nLast failed: ${firstDoc.file_path}`;
                            // Include error message in UI if available
                            if (firstDoc.error_msg) {
                              // Truncate long error messages for UI display
                              const shortError = firstDoc.error_msg.length > 500 
                                ? firstDoc.error_msg.substring(0, 500) + '...'
                                : firstDoc.error_msg;
                              errorDetails += `\nError: ${shortError}`;
                            }
                          }
                        }
                      }
                    } catch (e) {
                      console.error('Failed to fetch failed document details:', e);
                      appendLog(`❌ Exception while fetching failed document details: ${e}`);
                    }
                    
                    // Always show error message, even if we couldn't fetch details
                    message.error({
                      content: `⚠️ ${failedDiff} document(s) failed to process. Please check the document list and server logs for details.${errorDetails}`,
                      duration: 10,
                      style: { maxWidth: '600px' }
                    });
                    appendLog(`⚠️ ${failedDiff} document(s) failed during processing. Check server logs for error details.`);
                    
                    // Refresh the document list to show failed status
                    await loadDocuments();
                    await loadStatusCounts();
                  }
                  
                  // Check for early stop AFTER failure detection
                  // Stop polling if no documents are pending or processing and we've checked at least twice
                  if (processingCount === 0 && pendingCount === 0 && pollCount >= 2) {
                    console.log(`[DocumentsTab] No documents pending or processing, stopping polling early`);
                    appendLog(`✅ No documents pending or processing, stopping polling early`);
                    
                    // Log current document statuses for debugging
                    if (documents.length > 0) {
                      console.log(`[DocumentsTab] Current documents in UI:`, documents.map(d => ({
                        file: d.file_path,
                        status: d.status
                      })));
                    }
                    
                    clearInterval(pollInterval);
                    // Force refresh to ensure UI shows latest status
                    await loadDocuments();
                    await loadStatusCounts();
                    return;
                  }
                }
              } catch (e) {
                console.error('Error polling for failed documents:', e);
              }
            }, 3000); // Poll every 3 seconds
          }, 2000);
      } else {
          const errorMsg = response.error?.message || 'Unknown error';
          appendLog(t('pages.knowledge.documents.errorScanning') + errorMsg);
          message.error({
            content: t('pages.knowledge.documents.errorScanning') + errorMsg,
            duration: 8,
            style: { maxWidth: '600px' }
          });
          throw new Error(errorMsg);
      }
    } catch (e: any) {
      const errorMsg = e?.message || String(e);
      appendLog(t('pages.knowledge.documents.errorScanning') + errorMsg);
      message.error({
        content: t('pages.knowledge.documents.errorScanning') + errorMsg,
        duration: 8,
        style: { maxWidth: '600px' }
      });
    }
  };

  const handleRefreshStatus = async () => {
    appendLog(t('pages.knowledge.documents.refreshingStatus'));
    await loadDocuments();
    await loadStatusCounts();
  };

  const handleClearCache = () => {
    modal.confirm({
      title: t('pages.knowledge.documents.clearCache'),
      content: t('pages.knowledge.documents.clearCacheConfirm'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      onOk: async () => {
        try {
          appendLog(t('pages.knowledge.documents.clearingCache'));
          const response = await get_ipc_api().lightragApi.clearCache();
          if (response.success) {
              const data = response.data as any;
              appendLog(data?.message || t('pages.knowledge.documents.cacheCleared'));
              
              // Show deleted items if available
              if (data?.deleted_items && data.deleted_items.length > 0) {
                appendLog(`Deleted ${data.deleted_items.length} items:`);
                data.deleted_items.forEach((item: string) => {
                  appendLog(`  - ${item}`);
                });
              }
              
              // Show errors if any
              if (data?.errors && data.errors.length > 0) {
                appendLog(`Errors (${data.errors.length}):`);
                data.errors.forEach((error: string) => {
                  appendLog(`  ⚠️ ${error}`);
                });
              }
              
              // Reload documents after clearing cache
              await loadDocuments();
              await loadStatusCounts();
              message.success(t('pages.knowledge.documents.cacheCleared'));
          } else {
              const errorMsg = response.error?.message || 'Unknown error';
              appendLog(t('pages.knowledge.documents.errorClearingCache') + errorMsg);
              message.error({
                content: t('pages.knowledge.documents.errorClearingCache') + errorMsg,
                duration: 8,
                style: { maxWidth: '600px' }
              });
              throw new Error(errorMsg);
          }
        } catch (e: any) {
          const errorMsg = e?.message || String(e);
          appendLog(t('pages.knowledge.documents.errorClearingCache') + errorMsg);
          message.error({
            content: t('pages.knowledge.documents.errorClearingCache') + errorMsg,
            duration: 8,
            style: { maxWidth: '600px' }
          });
        }
      }
    });
  };
  
  const handleClearLog = () => {
    setLog('');
  };

  const handleDeleteDocument = (doc: Document) => {
    const titleKey = 'pages.knowledge.documents.deleteDocument';
    const titleTrans = t(titleKey);
    // If translation is missing (returns key), fallback to Chinese
    const title = titleTrans === titleKey ? '删除文档' : titleTrans;

    modal.confirm({
      title: title,
      content: t('pages.knowledge.documents.deleteDocumentConfirm', { filePath: doc.file_path }),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      onOk: async () => {
        try {
          appendLog(t('pages.knowledge.documents.deletingDocument', { filePath: doc.file_path }));
          // Pass 'id' as required by the updated backend handler
          const response = await get_ipc_api().lightragApi.deleteDocument({ id: doc.id });
          if (response.success) {
              appendLog(t('pages.knowledge.documents.documentDeleted'));
              message.success(t('pages.knowledge.documents.documentDeleted'));
              // Reload documents
              await loadDocuments();
              await loadStatusCounts();
          } else {
              const errorMsg = response.error?.message || 'Unknown error';
              appendLog(t('pages.knowledge.documents.errorDeletingDocument') + errorMsg);
              message.error({
                content: t('pages.knowledge.documents.errorDeletingDocument') + errorMsg,
                duration: 8,
                style: { maxWidth: '600px' }
              });
              throw new Error(errorMsg);
          }
        } catch (e: any) {
          const errorMsg = e?.message || String(e);
          appendLog(t('pages.knowledge.documents.errorDeletingDocument') + errorMsg);
          message.error({
            content: t('pages.knowledge.documents.errorDeletingDocument') + errorMsg,
            duration: 8,
            style: { maxWidth: '600px' }
          });
        }
      }
    });
  };

  const getStatusColor = (status: string) => {
    switch (status?.toUpperCase()) {
      case 'PROCESSED': return token.colorSuccess;
      case 'PROCESSING': return token.colorWarning;
      case 'PENDING': return token.colorTextTertiary;
      case 'FAILED': return token.colorError;
      default: return token.colorText;
    }
  };

  const getStatusText = (status: string) => {
    switch (status?.toUpperCase()) {
      case 'PROCESSED': return t('pages.knowledge.documents.completed');
      case 'PROCESSING': return t('pages.knowledge.documents.processing');
      case 'PENDING': return t('pages.knowledge.documents.pending');
      case 'FAILED': return t('pages.knowledge.documents.failed');
      default: return status;
    }
  };

  const handleStatusFilterChange = (status: string) => {
    setStatusFilter(status === 'ALL' ? null : status);
    setCurrentPage(1); // Reset to first page on filter change
  };

  return (
    <div style={{ 
      height: '100%', 
      overflow: 'auto'
    }}>
      {contextHolder}
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
          <button className="ec-btn" onClick={handleClearCache} title={t('pages.knowledge.documents.clearCache')}>
            <ClearOutlined /> {t('pages.knowledge.documents.clearCache')}
          </button>
          <button className="ec-btn" onClick={handleClearLog} title={t('pages.knowledge.documents.clearLog')}>
            {t('pages.knowledge.documents.clearLog')}
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
                  <FolderOpenOutlined /> {t('pages.knowledge.documents.selectFilesWithCount', { count: selectedFiles.length })}
                </button>
                <button className="ec-btn ec-btn-primary" onClick={handleIngestFiles} disabled={selectedFiles.length === 0}>
                  <UploadOutlined /> {t('pages.knowledge.documents.ingest')}
                </button>
              </div>
              {selectedFiles.length > 0 && (
                <div style={{ 
                  marginTop: 8, 
                  padding: '8px 12px', 
                  background: token.colorBgLayout, 
                  borderRadius: 6,
                  maxHeight: 120,
                  overflowY: 'auto',
                  fontSize: 12,
                  color: token.colorTextSecondary,
                  border: `1px solid ${token.colorBorderSecondary}`
                }}>
                  {selectedFiles.map((path, i) => (
                    <div key={i} style={{ 
                      whiteSpace: 'nowrap', 
                      overflow: 'hidden', 
                      textOverflow: 'ellipsis',
                      lineHeight: '20px'
                    }} title={path}>
                      {path}
                    </div>
                  ))}
                </div>
              )}
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
                  <FolderOpenOutlined /> {t('pages.knowledge.documents.browse')}
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
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="ec-btn" onClick={handleRefreshStatus} title={t('common.refresh')}>
              <UnorderedListOutlined /> {t('common.refresh') || 'Refresh'}
            </button>
            <Select 
              defaultValue="ALL" 
              style={{ width: 160 }} 
              onChange={handleStatusFilterChange}
              options={[
                { value: 'ALL', label: `${t('pages.knowledge.documents.all') || 'All'} (${statusCounts.all})` },
                { value: 'PROCESSED', label: `${t('pages.knowledge.documents.completed')} (${statusCounts.PROCESSED})` },
                { value: 'PROCESSING', label: `${t('pages.knowledge.documents.processing')} (${statusCounts.PROCESSING})` },
                { value: 'PENDING', label: `${t('pages.knowledge.documents.pending')} (${statusCounts.PENDING})` },
                { value: 'FAILED', label: `${t('pages.knowledge.documents.failed')} (${statusCounts.FAILED})` },
              ]}
            />
          </div>
        </div>

        {/* Table */}
        <div style={{ 
          height: '60vh',
          minHeight: 200,
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
            gridTemplateColumns: '1fr 120px 150px 100px', 
            gap: 8, 
            padding: '12px 16px',
            background: isDark ? token.colorBgTextHover : token.colorBgLayout,
            borderBottom: `1px solid ${token.colorBorder}`,
            fontWeight: 600,
            fontSize: 13,
            color: token.colorText
          }}>
            <div>{t('pages.knowledge.documents.fileName')}</div>
            <div style={{ textAlign: 'center' }}>{t('common.status')}</div>
            <div style={{ textAlign: 'center' }}>{t('pages.knowledge.documents.lastUpdated')}</div>
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
              {t('common.loading')}
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
                <div key={doc.id || doc.file_path || idx} style={{ 
                  display: 'grid', 
                  gridTemplateColumns: '1fr 120px 150px 100px', 
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
                    {getStatusText(doc.status)}
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
                      onClick={() => handleDeleteDocument(doc)}
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
                      {t('common.delete')}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
          
          {/* Pagination Footer */}
          <div style={{
            padding: '12px 16px',
            borderTop: `1px solid ${token.colorBorderSecondary}`,
            display: 'flex',
            justifyContent: 'flex-end'
          }}>
            <Pagination 
              current={currentPage} 
              pageSize={pageSize} 
              total={totalDocs} 
              onChange={(page, size) => {
                setCurrentPage(page);
                setPageSize(size);
              }}
              size="small"
              showTotal={(total) => t('pages.knowledge.documents.totalItems', { total })}
            />
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
        {log ? (
          <pre
            style={{
              margin: 0,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}
          >
            {log}
          </pre>
        ) : (
          <span style={{ opacity: 0.5, color: token.colorTextTertiary }}>
            {t('pages.knowledge.documents.consoleOutput')}
          </span>
        )}
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
